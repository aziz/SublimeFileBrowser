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


def show(window, path, view_id=None, ignore_existing=False, single_pane=False, goto=None):
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
        any_path  = lambda v: v.score_selector(0, "text.dired") > 0
        view = first(window.views(), any_path if single_pane else same_path)

    if not view:
        view = window.new_file()
        view.set_scratch(True)

    if path == os.sep:
        view_name = os.sep
    else:
        view_name = basename(path.rstrip(os.sep))

    name = u"𝌆 {0}".format(view_name)

    view.set_name(name)
    view.settings().set('dired_path', path)
    view.settings().set('dired_rename_mode', False)
    window.focus_view(view)
    view.run_command('dired_refresh', { 'goto': goto })
