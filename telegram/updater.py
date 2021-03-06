#!/usr/bin/env python
#
# A library that provides a Python interface to the Telegram Bot API
# Copyright (C) 2015-2016
# Leandro Toledo de Souza <devs@python-telegram-bot.org>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser Public License for more details.
#
# You should have received a copy of the GNU Lesser Public License
# along with this program.  If not, see [http://www.gnu.org/licenses/].


"""This module contains the class Updater, which tries to make creating
Telegram bots intuitive."""

import logging
import os
import ssl
from threading import Thread, Lock
from time import sleep
import subprocess
from signal import signal, SIGINT, SIGTERM, SIGABRT
from telegram import (Bot, TelegramError, dispatcher, Dispatcher,
                      NullHandler, JobQueue, UpdateQueue)
from telegram.utils.webhookhandler import (WebhookServer, WebhookHandler)

try:
    from urllib2 import URLError
except ImportError:
    from urllib.error import URLError

H = NullHandler()
logging.getLogger(__name__).addHandler(H)


class Updater:
    """
    This class, which employs the Dispatcher class, provides a frontend to
    telegram.Bot to the programmer, so they can focus on coding the bot. It's
    purpose is to receive the updates from Telegram and to deliver them to said
    dispatcher. It also runs in a separate thread, so the user can interact
    with the bot, for example on the command line. The dispatcher supports
    handlers for different kinds of data: Updates from Telegram, basic text
    commands and even arbitrary types.
    The updater can be started as a polling service or, for production, use a
    webhook to receive updates. This is achieved using the WebhookServer and
    WebhookHandler classes.


    Attributes:

    Args:
        token (Optional[str]): The bot's token given by the @BotFather
        base_url (Optional[str]):
        workers (Optional[int]): Amount of threads in the thread pool for
            functions decorated with @run_async
        bot (Optional[Bot]):

    Raises:
        ValueError: If both `token` and `bot` are passed or none of them.
    """

    def __init__(self,
                 token=None,
                 base_url=None,
                 workers=4,
                 bot=None,
                 job_queue_tick_interval=1.0):
        if (token is None) and (bot is None):
            raise ValueError('`token` or `bot` must be passed')
        if (token is not None) and (bot is not None):
            raise ValueError('`token` and `bot` are mutually exclusive')

        if bot is not None:
            self.bot = bot
        else:
            self.bot = Bot(token, base_url)
        self.update_queue = UpdateQueue()
        self.job_queue = JobQueue(self.bot, job_queue_tick_interval)
        self.dispatcher = Dispatcher(self.bot, self.update_queue,
                                     workers=workers)
        self.last_update_id = 0
        self.logger = logging.getLogger(__name__)
        self.running = False
        self.is_idle = False
        self.httpd = None
        self.__lock = Lock()

    def start_polling(self, poll_interval=0.0, timeout=10, network_delay=2):
        """
        Starts polling updates from Telegram.

        Args:
            poll_interval (Optional[float]): Time to wait between polling
                updates from Telegram in seconds. Default is 0.0
            timeout (Optional[float]): Passed to Bot.getUpdates
            network_delay (Optional[float]): Passed to Bot.getUpdates

        Returns:
            Queue: The update queue that can be filled from the main thread
        """

        with self.__lock:
            if not self.running:
                self.running = True

                # Create Thread objects
                dispatcher_thread = Thread(target=self.dispatcher.start,
                                           name="dispatcher")
                updater_thread = Thread(target=self._start_polling,
                                        name="updater",
                                        args=(poll_interval,
                                              timeout,
                                              network_delay))

                # Start threads
                dispatcher_thread.start()
                updater_thread.start()

                # Return the update queue so the main thread can insert updates
                return self.update_queue

    def start_webhook(self,
                      listen='127.0.0.1',
                      port=80,
                      url_path='',
                      cert=None,
                      key=None):
        """
        Starts a small http server to listen for updates via webhook. If cert
        and key are not provided, the webhook will be started directly on
        http://listen:port/url_path, so SSL can be handled by another
        application. Else, the webhook will be started on
        https://listen:port/url_path

        Args:
            listen (Optional[str]): IP-Address to listen on
            port (Optional[int]): Port the bot should be listening on
            url_path (Optional[str]): Path inside url
            cert (Optional[str]): Path to the SSL certificate file
            key (Optional[str]): Path to the SSL key file

        Returns:
            Queue: The update queue that can be filled from the main thread
        """

        with self.__lock:
            if not self.running:
                self.running = True

                # Create Thread objects
                dispatcher_thread = Thread(target=self.dispatcher.start,
                                           name="dispatcher")
                updater_thread = Thread(target=self._start_webhook,
                                        name="updater",
                                        args=(listen,
                                              port,
                                              url_path,
                                              cert,
                                              key))

                # Start threads
                dispatcher_thread.start()
                updater_thread.start()

                # Return the update queue so the main thread can insert updates
                return self.update_queue

    def _start_polling(self, poll_interval, timeout, network_delay):
        """
        Thread target of thread 'updater'. Runs in background, pulls
        updates from Telegram and inserts them in the update queue of the
        Dispatcher.
        """

        current_interval = poll_interval
        self.logger.info('Updater thread started')

        # Remove webhook
        self.bot.setWebhook(webhook_url=None)

        while self.running:
            try:
                updates = self.bot.getUpdates(self.last_update_id,
                                              timeout=timeout,
                                              network_delay=network_delay)
                if not self.running:
                    if len(updates) > 0:
                        self.logger.info('Updates ignored and will be pulled '
                                         'again on restart.')
                    break

                for update in updates:
                    self.update_queue.put(update)
                    self.last_update_id = update.update_id + 1
                    current_interval = poll_interval

                sleep(current_interval)
            except TelegramError as te:
                # Put the error into the update queue and let the Dispatcher
                # broadcast it
                self.update_queue.put(te)
                sleep(current_interval)

            except URLError as e:
                self.logger.error("Error while getting Updates: %s" % e)
                # increase waiting times on subsequent errors up to 30secs
                if current_interval == 0:
                    current_interval = 1
                elif current_interval < 30:
                    current_interval += current_interval / 2
                elif current_interval > 30:
                    current_interval = 30

        self.logger.info('Updater thread stopped')

    def _start_webhook(self, listen, port, url_path, cert, key):
        self.logger.info('Updater thread started')
        use_ssl = cert is not None and key is not None
        url_path = "/%s" % url_path

        # Create and start server
        self.httpd = WebhookServer((listen, port), WebhookHandler,
                                   self.update_queue, url_path)

        if use_ssl:
            # Check SSL-Certificate with openssl, if possible
            try:
                exit_code = subprocess.call(["openssl", "x509", "-text",
                                             "-noout", "-in", cert],
                                            stdout=open(os.devnull, 'wb'),
                                            stderr=subprocess.STDOUT)
            except OSError:
                exit_code = 0

            if exit_code is 0:
                try:
                    self.httpd.socket = ssl.wrap_socket(self.httpd.socket,
                                                        certfile=cert,
                                                        keyfile=key,
                                                        server_side=True)
                except ssl.SSLError as error:
                    raise TelegramError(str(error))
            else:
                raise TelegramError('SSL Certificate invalid')

        self.httpd.serve_forever(poll_interval=1)
        self.logger.info('Updater thread stopped')

    def stop(self):
        """
        Stops the polling/webhook thread, the dispatcher and the job queue
        """

        self.job_queue.stop()
        with self.__lock:
            if self.running:
                self.running = False
                self.logger.info('Stopping Updater and Dispatcher...')
                self.logger.debug('This might take a long time if you set a '
                                  'high value as polling timeout.')

                if self.httpd:
                    self.logger.info(
                        'Waiting for current webhook connection to be '
                        'closed... Send a Telegram message to the bot to exit '
                        'immediately.')
                    self.httpd.shutdown()
                    self.httpd = None

                self.logger.debug("Requesting Dispatcher to stop...")
                self.dispatcher.stop()
                while dispatcher.running_async > 0:
                    sleep(1)

                self.logger.debug("Dispatcher stopped.")

    def signal_handler(self, signum, frame):
        self.is_idle = False
        self.stop()

    def idle(self, stop_signals=(SIGINT, SIGTERM, SIGABRT)):
        """
        Blocks until one of the signals are received and stops the updater

        Args:
            stop_signals: Iterable containing signals from the signal module
                that should be subscribed to. Updater.stop() will be called on
                receiving one of those signals. Defaults to (SIGINT, SIGTERM,
                SIGABRT)
        """
        for sig in stop_signals:
            signal(sig, self.signal_handler)

        self.is_idle = True

        while self.is_idle:
            sleep(1)
