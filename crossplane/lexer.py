# -*- coding: utf-8 -*-
import itertools
import io

from .errors import NgxParserSyntaxError

EXTERNAL_LEXERS = {}

def _iterescape(iterable):
    chars = iter(iterable)
    for char in chars:
        if char == '\\':
            char = char + next(chars)
        yield char


def _iterlinecount(iterable):
    line = 1
    chars = iter(iterable)
    for char in chars:
        if char.endswith('\n'):
            line += 1
        yield (char, line)


def _lex_file_object(file_obj):
    """Generates token tuples from an nginx config file object"""
    token = ''  # the token buffer
    token_line = 0  # the line the token starts on
    next_token_is_directive = True

    it = itertools.chain.from_iterable(file_obj)
    it = _iterescape(it)  # treat escaped characters differently
    it = _iterlinecount(it)  # count the number of newline characters

    for char, line in it:
        # handle whitespace
        if char.isspace():
            # if token complete yield it and reset token buffer
            if token:
                yield (token, token_line)
                if next_token_is_directive and token in EXTERNAL_LEXERS:
                    for custom_lexer_token in EXTERNAL_LEXERS[token](it, token):
                        yield custom_lexer_token
                        next_token_is_directive = True
                else:
                    next_token_is_directive = False
                token = ''

            # disregard until char isn't a whitespace character
            while char.isspace():
                char, line = next(it)

        # if starting comment
        if not token and char == '#':
            while not char.endswith('\n'):
                token = token + char
                char, _ = next(it)
            yield (token, line)
            token = ''
            continue

        if not token:
            token_line = line

        # handle parameter expansion syntax (ex: "${var[@]}")
        if token and token[-1] == '$' and char == '{':
            next_token_is_directive = False
            while token[-1] != '}' and not char.isspace():
                token += char
                char, line = next(it)

        # if a quote is found, add the whole string to the token buffer
        if char in ('"', "'"):
            if token:
                yield (token, token_line)
                token = ''

            quote = char
            char, line = next(it)
            while char != quote:
                token += quote if char == '\\' + quote else char
                char, line = next(it)

            yield (token, token_line)
            if next_token_is_directive and token in EXTERNAL_LEXERS:
                for custom_lexer_token in EXTERNAL_LEXERS[token](it, token):
                    yield custom_lexer_token
                    next_token_is_directive = True
            else:
                next_token_is_directive = False
            token = ''

            continue

        # handle special characters that are treated like full tokens
        if char in ('{', '}', ';'):
            # if token complete yield it and reset token buffer
            if token:
                yield (token, token_line)
                token = ''

            # this character is a full token so yield it now
            yield (char, line)
            next_token_is_directive = True
            continue

        # append char to the token buffer
        token += char


def _balance_braces(tokens, filename=None):
    """Raises syntax errors if braces aren't balanced"""
    depth = 0

    for token, line in tokens:
        if token == '}':
            depth -= 1
        elif token == '{':
            depth += 1

        # raise error if we ever have more right braces than left
        if depth < 0:
            reason = 'unexpected "}"'
            raise NgxParserSyntaxError(reason, filename, line)
        else:
            yield token, line

    # raise error if we have less right braces than left at EOF
    if depth > 0:
        reason = 'unexpected end of file, expecting "}"'
        raise NgxParserSyntaxError(reason, filename, line)


def lex(filename):
    """Generates tokens from an nginx config file"""
    with io.open(filename, mode='r', encoding='utf-8') as f:
        it = _lex_file_object(f)
        it = _balance_braces(it, filename)
        for token, line in it:
            yield token, line


def register_external_lexer(directives, lexer):
    for directive in directives:
        EXTERNAL_LEXERS[directive] = lexer
