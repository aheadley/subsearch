#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import print_function

import logging
import re
import multiprocessing
import functools
import json
import random
import time
from html.parser import HTMLParser

import sopel.module
import sopel.tools
import sopel.logger
from sopel.config.types import StaticSection, ValidatedAttribute, ChoiceAttribute, ListAttribute
import requests

CONFIG_NAME = 'sonar2'

log = sopel.logger.get_logger(CONFIG_NAME)
log.setLevel(logging.DEBUG)

def multiprocessify(func):
    @functools.wraps(func)
    def wrapper(*pargs, **kwargs):
        return multiprocessing.Process(target=func, args=pargs, kwargs=kwargs)
    return wrapper

def getWorkerLogger(worker_name, level=logging.DEBUG):
    logging.basicConfig()
    log = logging.getLogger('sopel.modules.{}.{}-{:05d}'.format(CONFIG_NAME, worker_name, os.getpid()))
    log.setLevel(level)
    return log

class Sonar2Section(StaticSection):
    base_url        = ValidatedAttribute('base_url', str)
    max_wait        = ValidatedAttribute('max_wait', float)

def setup(bot):
    bot.config.define_section(CONFIG_NAME, Sonar2Section)

    if not bot.memory.contains(CONFIG_NAME):
        bot.memory[CONFIG_NAME] = sopel.tools.SopelMemory()

class SonarApi:
    def __init__(self, base_url):
        self._base_url = base_url

    def search(query, page=0):
        return requests.post(self._base_url + '/api/search', json={
            'query': query,
            }).json()

    def render(event_id, render_type):
        return requests.put(self._base_url + '/api/render', json={
            'event_id': event_id,
            'type': render_type,
            }).json()

    def render_status(task_id):
        return requests.get(self._base_url + '/api/render/' + task_id).json()

def weighted_random_choice(choices, weight=lambda c: 1.0):
    ratio = 1.0 / sum(weight(c) for c in choices)
    n = random.random()
    for w, v in ((weight(c), c) for c in choices):
        n -= (w * ratio)
        if n <= 0.0:
            return v
    else:
        return max(choices, key=weight)

htmlp = HTMLParser()
def format_event(event):
    message = '"{}" -- {} #{} @{:1.1f}'.format(
        htmlp.unescape(event['plaintext']),
        htmlp.unescape(event['episode']['series_name']).strip(),
        htmlp.unescape(event['episode']['episode_number']).strip(),
        event['episode']['timestamp'],
    )
    return message

@sopel.module.commands('sonar')
def cmd_sonar(bot, trigger):
    text_only = False
    render_type = 'image'
    words = trigger.group(2).strip()
    if '-webm' in words:
        render_type = 'video'
        words = words.replace('-webm', '').strip()
    if '-text' in words:
        text_only = True
        words = words.replace('-text', '').strip()

    if 'api' not in bot.memory[CONFIG_NAME]:
        bot.memory[CONFIG_NAME]['api'] = SonarApi(bot.config.sonar2.base_url)
    api = bot.memory[CONFIG_NAME]['api']

    try:
        results = api.search(query)
        if results:
            chosen_result = weighted_random_choice(results, weight=lambda c: c['score'])
            message = format_event(chosen_result)
            if text_only:
                bot.reply(message)
                return
            task_id = api.render(chosen_result['event_id'], render_type)['task_id']

            start = time.time()
            sleep_time = 20.0
            render_status = api.render_status(task_id)
            while not (render_status['finished'] or render_status['failed']):
                if time.time() - start > bot.config.sonar2.max_wait:
                    bot.reply(message + ' <render timeout>')
                    return
                time.sleep(sleep_time)
                sleep_time = max(sleep_time * 0.75, 5.0)
                render_status = api.render_status(task_id)
            if render_status['failed']:
                bot.reply(message + ' <render failed>')
            else:
                bot.reply(message + ' <{}/v/{}>'.format(bot.config.sonar2.base_url, task_id))
        else:
            bot.reply('Meme harder scrub')
    except Exception as err:
        log.exception(err)
        bot.reply('Something went very wrong: %s' % err) 
cmd_animeme.priority = 'medium'
