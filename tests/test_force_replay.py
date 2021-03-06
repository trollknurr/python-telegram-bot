#!/usr/bin/env python
# encoding: utf-8
#
# A library that provides a Python interface to the Telegram Bot API
# Copyright (C) 2015-2016
# Leandro Toledo de Souza <devs@python-telegram-bot.org>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see [http://www.gnu.org/licenses/].

"""This module contains a object that represents Tests for Telegram ForceReply"""

import unittest
import sys
sys.path.append('.')

import telegram
from tests.base import BaseTest


class ForceReplyTest(BaseTest, unittest.TestCase):
    """This object represents Tests for Telegram ForceReply."""

    def setUp(self):
        self.force_reply = True
        self.selective = True

        self.json_dict = {
            'force_reply': self.force_reply,
            'selective': self.selective,
        }
        
    def test_send_message_with_force_reply(self):
        """Test telegram.Bot sendMessage method with ForceReply"""
        print('Testing bot.sendMessage - with ForceReply')

        message = self._bot.sendMessage(self._chat_id,
                                        'Моё судно на воздушной подушке полно угрей',
                                        reply_markup=telegram.ForceReply.de_json(self.json_dict))
        
        self.assertTrue(self.is_json(message.to_json()))
        self.assertEqual(message.text, u'Моё судно на воздушной подушке полно угрей')

    def test_force_reply_de_json(self):
        """Test ForceReply.de_json() method"""
        print('Testing ForceReply.de_json()')

        force_reply = telegram.ForceReply.de_json(self.json_dict)

        self.assertEqual(force_reply.force_reply, self.force_reply)
        self.assertEqual(force_reply.selective, self.selective)
        
    def test_force_reply_to_json(self):
        """Test ForceReply.to_json() method"""
        print('Testing ForceReply.to_json()')

        force_reply = telegram.ForceReply.de_json(self.json_dict)

        self.assertTrue(self.is_json(force_reply.to_json()))
        
    def test_force_reply_to_dict(self):
        """Test ForceReply.to_dict() method"""
        print('Testing ForceReply.to_dict()')

        force_reply = telegram.ForceReply.de_json(self.json_dict)

        self.assertEqual(force_reply['force_reply'], self.force_reply)
        self.assertEqual(force_reply['selective'], self.selective)
                        
if __name__ == '__main__':
    unittest.main()
