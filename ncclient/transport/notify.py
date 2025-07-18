# Copyright 2009 Shikhar Bhushan
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from ncclient.xml_ import to_ele
from lxml import etree

class Notification(object):
    def __init__(self, raw):
        self._raw = raw
        self._root_ele = to_ele(raw)

    @property
    def notification_ele(self):
        return self._root_ele

    @property
    def notification_xml(self):
        return self._raw

class NotificationM(object):
    def __init__(self, raw):
        self._raw = raw
        self._root_ele = to_ele(raw)
        for elm in etree.ElementChildIterator(self._root_ele):
            localname = etree.QName(elm).localname
            if localname == 'eventTime':
                self._eventTime = elm.text
            else:
                self._ntfname = localname

    @property
    def notification_ele(self):
        return self._root_ele

    @property
    def notification_xml(self):
        return self._raw

    @property
    def event_time(self):
        return self._eventTime

    @property
    def notifcaiton_name(self):
        return self._ntfname
