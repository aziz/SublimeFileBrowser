#!/usr/bin/python
# -*- coding: utf-8 -*-

# Internal-only commands for dealing with the directory prompt.  Due to Sublime Text's quirky
# design we need to re-issue commands over and over during a single prompt.

import sublime
from sublime import Region
from sublime_plugin import WindowCommand, EventListener, TextCommand
import os
from os.path import basename, join, isdir, dirname, expanduser

map_window_to_ctx = {}
# Map from window id that is displaying a prompt to its prompt context object.


def start(msg, window, path, callback):
    """
    Starts the prompting process.
    """
    if not(path.endswith(os.sep) or path == os.sep):
        path += os.sep
    path = expanduser(path)
    map_window_to_ctx[window.id()] = PromptContext(msg, path, callback)
    window.run_command('dired_prompt')


class PromptContext:
    def __init__(self, msg, path, callback):
        self.msg = msg
        self.path = path
        # The path we are completing.  This is updated as the user types, so it will be an
        # invalid path at times.

        self.callback = callback

        self.completion_view = None

    def __repr__(self):
        return '{} {} view:{}'.format(self.path, bool(self.completion_view))


class DiredPromptCommand(WindowCommand):
    """
    An internal-only command that separates prompt handling from external commands since each
    tab completion requires another command.

    A prompt context must already be registered in map_window_to_ctx when this is executed.
    """
    def run(self):
        ctx = map_window_to_ctx[self.window.id()]
        self.window.show_input_panel(ctx.msg, ctx.path, self.on_done, self.on_change, self.on_cancel)

    def on_done(self, value):
        ctx = map_window_to_ctx.pop(self.window.id(), None)
        self._close_completions()
        ctx.callback(ctx.path)

    def on_cancel(self):
        self._close_completions()

    def on_change(self, value):
        # Keep the path in the ctx up to date in case Tab is pressed.  It will cancel this completion
        # and start another.
        ctx = map_window_to_ctx.get(self.window.id())
        if ctx:
            ctx.path = value

    def _close_completions(self):
        ctx = map_window_to_ctx.pop(self.window.id(), None)
        if ctx and ctx.completion_view:
            self.window.focus_view(ctx.completion_view)
            self.window.run_command('close_file')

class DiredEventListener(EventListener):
    def on_query_context(self, view, key, operator, operand, match_all):
        if not map_window_to_ctx or not key.startswith('dired_'):
            return None
        if key == 'dired_complete':
            return True
        return False


class DiredCompleteCommand(WindowCommand):
    """
    An internal command executed when the user has pressed Tab in our directory prompt.

    Since a prompt is already in progress, a completion info must already be registered for
    this window.  Update the path, kill the current prompt, and reprompt with the new path.
    """
    def _needs_sep(self, path):
        """
        Returns True if the current value is a complete directory name without a trailing
        separator, and there are no other possible completions.
        """
        if not isdir(path) or path.endswith(os.sep):
            return False

        partial = basename(path)
        path    = dirname(path)
        if any(n for n in os.listdir(dirname(path)) if n != partial and n.startswith(partial) and isdir(join(path, n))):
            # There are other completions.
            return False

        return True

    def _parse_split(self, path):
        """
        Split the path into the directory to search and the prefix to match in that directory.

        If the path is completely invalid, (None, None) is returned.
        """
        prefix = ''

        if not path.endswith(os.sep):
            prefix = basename(path)
            path   = dirname(path)

        if not isdir(path):
            return (None, None)

        return (path, prefix)


    def _close_completions(self, ctx):
        if ctx.completion_view:
            self.window.focus_view(ctx.completion_view)
            self.window.run_command('close_file')
            ctx.completion_view = None


    def run(self):
        ctx = map_window_to_ctx.get(self.window.id())
        if not ctx:
            return

        path = expanduser(ctx.path)
        path, prefix = self._parse_split(path)
        if path is None:
            print('Invalid:', ctx.path)
            return

        completions = [ n for n in os.listdir(path) if n.startswith(prefix) and isdir(join(path, n)) ]

        if len(completions) == 0:
            sublime.status_message('No matches')
            self._close_completions(ctx)
            return

        if len(completions) == 1:
            ctx.path = join(path, completions[0]) + os.sep
            self.window.run_command('dired_prompt')
            self._close_completions(ctx)
            return

        common = os.path.commonprefix(completions)
        if common and common > prefix:
            ctx.path = join(path, common)
            self.window.run_command('dired_prompt')
            self._close_completions(ctx)
            return

        # There are multiple possibilities.  Display a completion view.

        if not ctx.completion_view:
            ctx.completion_view = self.window.new_file()
            ctx.completion_view.set_scratch(True)
            ctx.completion_view.set_syntax_file('Packages/FileBrowser/dired.hidden-tmLanguage')
            ctx.completion_view.settings().set("gutter", False)
            ctx.completion_view.set_name('*completions*')
        ctx.completion_view.run_command('dired_show_completions', { "completions": completions })
        self.window.focus_view(ctx.completion_view)


class DiredShowCompletionsCommand(TextCommand):
    def run(self, edit, completions=None):
        self.view.erase(edit, Region(0, self.view.size()))
        self.view.insert(edit, 0, '\n'.join(completions))

