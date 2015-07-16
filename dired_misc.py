# coding: utf-8

'''This module contains miscellaneous commands for additional functionality.
    Suppose these things are useful, but not essential.
'''

from __future__ import print_function
import sublime
from sublime import Region
from sublime_plugin import TextCommand, EventListener
import os, subprocess, sys, threading, glob
from os.path import dirname, isfile, exists, join, normpath

ST3 = int(sublime.version()) >= 3000

if ST3:
    from .common import DiredBaseCommand, set_proper_scheme, hijack_window, NT, OSX
    MARK_OPTIONS = sublime.DRAW_NO_OUTLINE
else:  # ST2 imports
    import locale
    from common import DiredBaseCommand, set_proper_scheme, hijack_window, NT, OSX
    MARK_OPTIONS = 0


class DiredFindInFilesCommand(TextCommand, DiredBaseCommand):
    def run(self, edit):
        self.index = self.get_all()
        path = self.path
        if path == 'ThisPC\\':
            path  = ''
            items = self.get_marked() or self.get_selected()
        else:
            items = self.get_marked()
        where = ', '.join(join(path, p) for p in items) or path or ''
        args  = {"panel": "find_in_files", "where": where, "replace": "", "reverse": "false"}
        sublime.active_window().run_command("show_panel", args)


# HELP ##############################################################

class DiredHelpCommand(TextCommand):
    def run(self, edit):
        view = self.view.window().new_file()
        view.settings().add_on_change('color_scheme', lambda: set_proper_scheme(view))
        view.set_name("Browse: shortcuts")
        view.set_scratch(True)
        view.settings().set('rulers', [])
        view.settings().set('syntax', 'Packages/FileBrowser/dired-help.hidden-tmLanguage')
        view.settings().set('line_numbers', False)
        view.run_command('dired_show_help')
        sublime.active_window().focus_view(view)


class DiredShowHelpCommand(TextCommand):
    def run(self, edit):
        COMMANDS_HELP = sublime.load_resource('Packages/FileBrowser/shortcuts.md') if ST3 else ''
        if not COMMANDS_HELP:
            dest = dirname(__file__)
            shortcuts = join(dest if dest != '.' else join(sublime.packages_path(), 'FileBrowser'), "shortcuts.md")
            COMMANDS_HELP = open(shortcuts, "r").read()
        self.view.erase(edit, Region(0, self.view.size()))
        self.view.insert(edit, 0, COMMANDS_HELP)
        self.view.sel().clear()
        self.view.set_read_only(True)


# OTHER #############################################################

class DiredToggleProjectFolder(TextCommand, DiredBaseCommand):
    def run(self, edit):
        if not ST3:
            return sublime.status_message('This feature is available only in Sublime Text 3')
        path = self.path.rstrip(os.sep)
        data = self.view.window().project_data() or {}
        data['folders'] = data.get('folders', {})
        folders = [f for f in data['folders'] if f['path'] != path]
        if len(folders) == len(data['folders']):
            folders.insert(0, {'path': path})
        data['folders'] = folders
        self.view.window().set_project_data(data)
        self.view.window().run_command('dired_refresh')


class DiredOnlyOneProjectFolder(TextCommand, DiredBaseCommand):
    def run(self, edit):
        if not ST3:
            return sublime.status_message('This feature is available only in Sublime Text 3')
        path = self.path.rstrip(os.sep)
        msg = u"Set '{0}' as only one project folder (will remove all other folders from project)?".format(path)
        if sublime.ok_cancel_dialog(msg):
            data = self.view.window().project_data() or {'folders': {}}
            data['folders'] = [{'path': path}]
            self.view.window().set_project_data(data)
            self.view.window().run_command('dired_refresh')


class DiredQuickLookCommand(TextCommand, DiredBaseCommand):
    """
    quick look current file in mac or open in default app on other OSs
    """
    def run(self, edit):
        self.index = self.get_all()
        files = self.get_marked() or self.get_selected(parent=False)
        if not files:
            return sublime.status_message('Nothing chosen')
        if OSX:
            cmd = ["qlmanage", "-p"]
            for filename in files:
                fqn = join(self.path, filename)
                cmd.append(fqn)
            subprocess.call(cmd)
        else:
            if NT:
                launch = lambda f: os.startfile(f)
            else:
                launch = lambda f: subprocess.call(['xdg-open', f])
            for filename in files:
                fqn = join(self.path, filename)
                launch(fqn)


class DiredOpenExternalCommand(TextCommand, DiredBaseCommand):
    """open dir/file in external file explorer"""
    def run(self, edit):
        path = self.path
        self.index = self.get_all()
        files = self.get_selected(parent=False)
        fname = join(path, files[0] if files else '')
        p, f  = os.path.split(fname.rstrip(os.sep))

        if not exists(fname):
            return sublime.status_message(u'Directory doesn’t exist “%s”' % path)

        if NT and path == 'ThisPC\\':
            if not ST3:
                fname = fname.encode(locale.getpreferredencoding(False))
            return subprocess.Popen('explorer /select,"%s"' % fname)

        if files:
            self.view.window().run_command("open_dir", {"dir": p, "file": f})
        else:
            self.view.window().run_command("open_dir", {"dir": path})


class DiredOpenInNewWindowCommand(TextCommand, DiredBaseCommand):
    def run(self, edit, project_folder=False):
        self.index = self.get_all()
        if project_folder:
            files = project_folder
        else:
            files = self.get_marked() or self.get_selected()
        items = []

        if ST3:  # sublime.executable_path() is not available in ST2
            executable_path = sublime.executable_path()
            if OSX:
                app_path = executable_path[:executable_path.rfind(".app/")+5]
                executable_path = app_path+"Contents/SharedSupport/bin/subl"
            items.append(executable_path)
            items.append("-n")

            for filename in files:
                fqn = join(self.path, filename)
                items.append(fqn)

            if NT:
                subprocess.Popen(items)
            else:
                subprocess.Popen(items, cwd=self.path)

        else:  # ST2
            items.append("-n")
            for filename in files:
                fqn = join(self.path or u'', filename)
                items.append(fqn)

            if OSX:
                try:
                    subprocess.Popen(['subl'] + items, cwd=self.path)
                except:
                    try:
                        subprocess.Popen(['sublime'] + items, cwd=self.path)
                    except:
                        app_path = subprocess.Popen(["osascript", "-e" "tell application \"System Events\" to POSIX path of (file of process \"Sublime Text 2\" as alias)"], stdout=subprocess.PIPE).communicate()[0].rstrip()
                        subl_path = "{0}/Contents/SharedSupport/bin/subl".format(app_path)
                        subprocess.Popen([subl_path] + items, cwd=self.path)
            elif NT:
                # 9200 means win8
                shell = True if sys.getwindowsversion()[2] < 9200 else False
                items = [i.encode(locale.getpreferredencoding(False)) if sys.getwindowsversion()[2] == 9200 else i for i in items]
                try:
                    subprocess.Popen(['subl'] + items, shell=shell)
                except:
                    try:
                        subprocess.Popen(['sublime'] + items, shell=shell)
                    except:
                        subprocess.Popen(['sublime_text.exe'] + items, shell=shell)
            else:
                try:
                    subprocess.Popen(['subl'] + items, cwd=self.path)
                except:
                    subprocess.Popen(['sublime'] + items, cwd=self.path)

        def run_on_new_window():
            settings = sublime.load_settings('dired.sublime-settings')
            open_on_jump = settings.get('dired_open_on_jump', 'left')

            if open_on_jump:
                options = {"immediate": True, "project": True}

                if open_on_jump in ['left', 'right']:
                    options["other_group"] = open_on_jump

                sublime.active_window().run_command("dired", options)

        sublime.set_timeout(run_on_new_window, 200)
        if not ST3:
            sublime.set_timeout(lambda: sublime.active_window().run_command("toggle_side_bar"), 200)


# EVENT LISTENERS ###################################################

class DiredHijackNewWindow(EventListener):
    def on_window_command(self, window, command_name, args):
        if command_name != "new_window":
            return
        hijack_window()


class DiredHideEmptyGroup(EventListener):
    def on_close(self, view):
        if not 'dired' in view.scope_name(0):
            return

        w = sublime.active_window()
        # check if closed view was a single one in group
        if ST3:
            single = not w.views_in_group(0) or not w.views_in_group(1)
        else:
            single = ([view.id()] == [v.id() for v in w.views_in_group(0)] or
                      [view.id()] == [v.id() for v in w.views_in_group(1)])
        if w.num_groups() == 2 and single:
            # without timeout ST may crash
            sublime.set_timeout(lambda: w.set_layout({"cols": [0.0, 1.0], "rows": [0.0, 1.0], "cells": [[0, 0, 1, 1]]}), 300)


class DiredMoveOpenOrNewFileToRightGroup(EventListener):
    def on_activated(self, view):
        '''
        Trick to prevent unexpected movements (e.g. when switching project in
        current window; or restart)
        Reason why the whole logic shall not be run on_activated, is
        user should be able to explicitly put any view in left group
        no matter what, e.g. using keybinding or drag&drop
        '''
        w = sublime.active_window()
        if w and any(v for v in w.views_in_group(0) if 'dired' in v.scope_name(0)):
            self.MOVE = True
        else:
            self.MOVE = False

    def on_new(self, view):
        if not self.MOVE:
            return
        w = sublime.active_window()
        if w.num_groups() < 2:
            return
        if any(v for v in w.views_in_group(0) if 'dired' in v.scope_name(0)):
            if w.active_group() == 0:
                # at this point views are exist, so we cannot avoid the use of
                # set_view_index, but ST2 return None if group has no views
                # ST3 return None if group has active image’s view
                avig1 = w.active_view_in_group(1)
                if avig1:
                    _group, active_view_index_in_other_group = w.get_view_index(avig1)
                    index = active_view_index_in_other_group + 1
                else:
                    index = 0
                sublime.set_timeout(lambda: w.set_view_index(view, 1, index), 1)

    def on_load(self, view):
        self.on_new(view)


# TOOLS #############################################################

class DiredCallVcs(TextCommand):
    def run(self, edit, path):
        CallVCS(self.view, path)


# TOOLS #############################################################

class CallVCS(DiredBaseCommand):
    '''
    this should be placed in common.py probably, but for some reason
    it doesnt work this way, so place it in main file for now
    '''
    def __init__(self, view, path):
        self.view = view
        self.vcs_state = dict(path=path)
        self.view.erase_regions('M')
        self.view.erase_regions('?')
        self.call_git(path)
        self.call_hg(path)
        self.watch_threads()

    def watch_threads(self):
        if not all(n in self.vcs_state for n in ['git', 'hg']):
            sublime.set_timeout(self.watch_threads, 100)
            return
        if 'changed_items' in self.vcs_state:
            self.vcs_colorized(self.vcs_state['changed_items'])

    def call_git(self, path):
        git = self.view.settings().get('git_path', '')
        if git:  # empty string disable git integration
            self.git_thread = threading.Thread(target=self.git_check, args=(path, git))
            self.git_thread.start()
        else:
            self.vcs_state.update(git=False)

    def git_check(self, path, git='git'):
        if any(c for c in '~*?[]$%' if c in git) and not isfile(git):
            match = glob.glob(os.path.expandvars(os.path.expanduser(git)))
            if match:
                git = match[0]
            else:
                sublime.error_message(u'FileBrowser:\n'
                    u'It seems like you use wildcards in\n\n"git_path": "%s".\n\n'
                    u'But the pattern cannot be found, please, fix it '
                    u'or use absolute path without wildcards.' % git)

        shell = True if NT else False
        try:
            p = subprocess.Popen([git, 'status', '-z'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=path, shell=shell)
            git_output = p.communicate()[0]
            p = subprocess.Popen([git, 'rev-parse', '--show-toplevel'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=path, shell=shell)
            root = p.communicate()[0].decode('utf-8').strip('\n')
        except:
            # on Windows exception is not being raised if cwd is not None and shell=True
            self.vcs_state.update(git=False)
        else:
            if git_output:
                git_output = str(git_output, 'utf-8').split('\x00') if ST3 else git_output.split('\00')
                new_values = dict((join(root, i[3:] if ST3 else unicode(i[3:], 'utf-8')), i[1]) for i in git_output if i != '')
                changed_items = self.vcs_state.get('changed_items', {})
                changed_items.update(new_values)
                self.vcs_state.update(git=True, changed_items=changed_items)
            else:
                self.vcs_state.update(git=False)

    def call_hg(self, path):
        hg = self.view.settings().get('hg_path', '')
        if hg:  # empty string disable hg integration
            self.hg_thread = threading.Thread(target=self.hg_check, args=(path, hg))
            self.hg_thread.start()
        else:
            self.vcs_state.update(hg=False)

    def hg_check(self, path, hg='hg'):
        if any(c for c in '~*?[]$%' if c in hg) and not isfile(hg):
            match = glob.glob(os.path.expandvars(os.path.expanduser(hg)))
            if match:
                hg = match[0]
            else:
                sublime.error_message(u'FileBrowser:\n'
                    u'It seems like you use wildcards in\n\n"hg_path": "%s".\n\n'
                    u'But the pattern cannot be found, please, fix it '
                    u'or use absolute path without wildcards.' % hg)

        shell = True if NT else False
        try:
            p = subprocess.Popen([hg, 'status'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=path, shell=shell)
            hg_output = p.communicate()[0]
            p = subprocess.Popen([hg, 'root'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=path, shell=shell)
            root = p.communicate()[0].decode('utf-8').strip('\n')
        except:
            # on Windows exception is not being raised if cwd is not None and shell=True
            self.vcs_state.update(hg=False)
        else:
            if hg_output:
                hg_output = str(hg_output, 'utf-8').split('\n') if ST3 else hg_output.split('\n')
                new_values = dict(( join(root,i[2:] if ST3 else unicode(i[2:], 'utf-8')), i[0]) for i in hg_output if i != '')
                changed_items = self.vcs_state.get('changed_items', {})
                changed_items.update(new_values)
                self.vcs_state.update(hg=True, changed_items=changed_items)
            else:
                self.vcs_state.update(hg=False)

    def vcs_colorized(self, changed_items):
        modified, untracked = [], []
        files_regions = dict((f, r) for f, r in zip(self.get_all(), self.view.split_by_newlines(Region(0, self.view.size()))))
        colorblind = self.view.settings().get('vcs_color_blind', False)
        offset = 1 if not colorblind else 0
        for fn in changed_items.keys():
            full_fn = normpath(fn)
            r = files_regions.get(full_fn, 0)
            if r:
                icon   = self._get_name_point(r) - 2
                r      = Region(icon, icon + offset)
                status = changed_items[fn]
                if status == 'M':
                    modified.append(r)
                elif status == '?':
                    untracked.append(r)
        if colorblind:
            self.view.add_regions('M', modified, 'item.colorblind.dired', '', MARK_OPTIONS | sublime.DRAW_EMPTY_AS_OVERWRITE)
            self.view.add_regions('?', untracked, 'item.colorblind.dired', '', MARK_OPTIONS | sublime.DRAW_EMPTY)
        else:
            self.view.add_regions('M', modified, 'item.modified.dired', '', MARK_OPTIONS)
            self.view.add_regions('?', untracked, 'item.untracked.dired', '', MARK_OPTIONS)
