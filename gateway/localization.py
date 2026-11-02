"""Translate service-owned API messages without changing user data."""
import json
from pathlib import Path
import re

MESSAGES=json.loads((Path(__file__).parent/'web/locales.json').read_text(encoding='utf-8'))


def translate_message(value, language):
    if not isinstance(value,str) or not language.lower().startswith('en'):
        return value
    if value in MESSAGES:
        return MESSAGES[value]
    for source,target in sorted(MESSAGES.items(),key=lambda item:len(item[0]),reverse=True):
        if source.endswith(': ') and value.startswith(source):
            return target+value[len(source):]
    match=re.fullmatch(r'(check_interval|fail_threshold|recover_threshold): допустимо целое число от (\d+) до (\d+)\.',value)
    if match:
        return f'{match[1]}: enter an integer from {match[2]} to {match[3]}.'
    return value
