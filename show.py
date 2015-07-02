#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import sublime
from os.path import basename

ST3 = int(sublime.version()) >= 3000

if ST3:
    from .common import first
else:
    from common import first


def set_proper_scheme(view):
    '''
    this is callback, it is not meant to be called directly
        view.settings().add_on_change('color_scheme', lambda: set_proper_scheme(view))
    set once, right after view is created
    _note_, color_scheme must not be set directly, but in a setting file
    '''
    # Since we cannot create file with syntax, there is moment when view has no settings,
    # but it is activated, so some plugins (e.g. Color Highlighter) set wrong color scheme
    if view.settings().get('dired_rename_mode', False):
        dired_settings = sublime.load_settings('dired-rename-mode.sublime-settings')
    else:
        dired_settings = sublime.load_settings('dired.sublime-settings')

    if view.settings().get('color_scheme') == dired_settings.get('color_scheme'):
        return

    view.settings().set('color_scheme', dired_settings.get('color_scheme'))


def calc_width(view):
    '''
    return float width, which must be
        0.0 < width < 1.0 (other values acceptable, but cause unfriendly layout)
    used in show() and "dired_select" command with other_group=True
    '''
    width = view.settings().get('dired_width', 0.3)
    if isinstance(width, float):
        width -= width//1  # must be less than 1
    elif isinstance(width, int if ST3 else long):  # assume it is pixels
        wport = view.viewport_extent()[0]
        width = 1 - round((wport - width) / wport, 2)
        if width >= 1:
            width = 0.9
    else:
        sublime.error_message(u'FileBrowser:\n\ndired_width set to '
                              u'unacceptable type "%s", please change it.\n\n'
                              u'Fallback to default 0.3 for now.' % type(width))
        width = 0.3
    return width or 0.1  # avoid 0.0


def show(window, path, view_id=None, ignore_existing=False, single_pane=False, goto=None, other_group=''):
    """
    Determines the correct view to use, creating one if necessary, and prepares it.
    """
    if not(path.endswith(os.sep) or path == os.sep):
        path += os.sep

    view = None
    if view_id:
        # The Goto command was used so the view is already known and its contents should be
        # replaced with the new path.
        view = first(window.views(), lambda v: v.id() == view_id)

    if not view and not ignore_existing:
        # See if a view for this path already exists.
        same_path = lambda v: v.settings().get('dired_path') == path
        # See if any reusable view exists in case of single_pane argument
        any_path = lambda v: v.score_selector(0, "text.dired") > 0
        view = first(window.views(), any_path if single_pane else same_path)

    if other_group:
        prev_focus = window.active_view()
        # simulate 'toggle sidebar':
        if prev_focus and 'dired' in prev_focus.scope_name(0):
            window.run_command('close_file')
            return

    if not view:
        view = window.new_file()
        view.settings().add_on_change('color_scheme', lambda: set_proper_scheme(view))
        view.set_syntax_file('Packages/FileBrowser/dired.hidden-tmLanguage')
        view.set_scratch(True)
        reset_sels = True
    else:
        reset_sels = path != view.settings().get('dired_path', '')

    nag = window.active_group()
    if other_group:
        group = 0 if other_group == 'left' else 1
        if window.num_groups() == 1:
            width = calc_width(view)
            cols = [0.0, width, 1.0] if other_group == 'left' else [0.0, 1-width, 1.0]
            window.set_layout({"cols": cols, "rows": [0.0, 1.0], "cells": [[0, 0, 1, 1], [1, 0, 2, 1]]})
        elif view:
            groups = window.num_groups()
            if groups <= 4 and nag < 2:
                group = 1 if nag == 0 else 0
            elif groups == 4 and nag >= 2:
                group = 3 if nag == 2 else 2
            else:
                group = nag - 1
        window.set_view_index(view, group, 0)
    else:
        group = nag

    # when other_group is left, we need move all views to right except FB view
    if nag == 0 and other_group == 'left' and group == 0:
        for v in reversed(window.views_in_group(nag)[1:]):
            window.set_view_index(v, 1, 0)

    if other_group and prev_focus:
        window.focus_view(prev_focus)

    if path == os.sep:
        view_name = os.sep
    else:
        view_name = basename(path.rstrip(os.sep))

    if ST3:
        name = u"𝌆 {0}".format(view_name)
    else:
        name = u"■ {0}".format(view_name)

    view.set_name(name)
    view.settings().set('dired_path', path)
    view.settings().set('dired_rename_mode', False)
    window.focus_view(view)
    view.run_command('dired_refresh', {'goto': goto, 'reset_sels': reset_sels})
