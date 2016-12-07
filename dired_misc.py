# coding: utf-8

'''This module contains miscellaneous commands for additional functionality.
    Suppose these things are useful, but not essential.
'''

from __future__ import print_function
import sublime, sublime_plugin
from sublime import Region
from sublime_plugin import TextCommand, EventListener
import glob
import math
import os
import subprocess
import sys
import threading
from os.path import dirname, isfile, isdir, exists, join, normpath, getsize, getctime, getatime, getmtime
from datetime import datetime

ST3 = int(sublime.version()) >= 3000

if ST3:
    from .common import DiredBaseCommand, set_proper_scheme, hijack_window, emit_event, NT, OSX, PARENT_SYM, sort_nicely
    MARK_OPTIONS = sublime.DRAW_NO_OUTLINE
    SYNTAX_EXTENSION = '.sublime-syntax'
else:  # ST2 imports
    import locale
    from common import DiredBaseCommand, set_proper_scheme, hijack_window, emit_event, NT, OSX, PARENT_SYM, sort_nicely
    MARK_OPTIONS = 0
    SYNTAX_EXTENSION = '.hidden-tmLanguage'
    sublime_plugin.ViewEventListener = object


def convert_size(size):
    if not size:
        return '0 B'
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size, 1024)))
    p = math.pow(1024, i)
    s = round(size / p, 2)
    return '%s %s' % (s, size_name[i])


def get_dates(path):
    try:
        created = datetime.fromtimestamp(getctime(path)).strftime('%d %b %Y, %H:%M:%S')
    except OSError as e:
        created = e
    try:
        accessed = datetime.fromtimestamp(getatime(path)).strftime('%d %b %Y, %H:%M:%S')
    except OSError as e:
        accessed = e
    try:
        modified = datetime.fromtimestamp(getmtime(path)).strftime('%d %b %Y, %H:%M:%S')
    except OSError as e:
        modified = e
    return created, accessed, modified


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
        view.settings().set('syntax', 'Packages/FileBrowser/dired-help' + SYNTAX_EXTENSION)
        view.settings().set('margin', 16)
        view.settings().set('line_numbers', False)
        view.settings().set('gutter', False)
        view.settings().set('fold_buttons', False)
        view.settings().set('draw_indent_guides', False)
        view.settings().set('word_wrap', False)
        view.settings().set('spell_check', False)
        view.settings().set('drag_text', False)
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
    def run(self, edit, preview=True, files=None):
        self.index = self.get_all()
        files = files or self.get_marked() or self.get_selected(parent=False)
        if not files:
            return sublime.status_message('Nothing chosen')
        if OSX and preview:
            cmd = ["qlmanage", "-p"]
            for filename in files:
                fqn = join(self.path, filename)
                cmd.append(fqn)
            subprocess.call(cmd)
        else:
            if OSX:
                launch = lambda f: subprocess.call(['open', f], cwd=dirname(f))
            elif NT:
                # the "" before filename is a trick for batch files and such
                launch = lambda f: subprocess.call('start "" "%s"' % f, shell=True, cwd=dirname(f))
            else:
                launch = lambda f: subprocess.call(['xdg-open', f], cwd=dirname(f))
            for filename in files:
                fqn = join(self.path, filename)
                launch(fqn)


class DiredOpenExternalCommand(TextCommand, DiredBaseCommand):
    """open dir/file in external file explorer"""
    def run(self, edit, fname=None):
        path = self.path
        if not fname:
            self.index = self.get_all()
            files = self.get_selected(parent=False)
            fname = join(path, files[0] if files else '')
        else:
            files = True
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
        if project_folder:
            files = project_folder
        else:
            self.index = self.get_all()
            files = self.get_marked(full=True) or self.get_selected(parent=False, full=True)

        if not files:
            return sublime.status_message('Nothing chosen')

        if ST3:
            self.launch_ST3(files)
        else:
            self.launch_ST2(files)

        def run_on_new_window():
            settings = sublime.load_settings('dired.sublime-settings')
            open_on_jump = settings.get('dired_open_on_jump', 'left')

            if open_on_jump:
                options = {"immediate": True, "project": True}

                if open_on_jump in ['left', 'right']:
                    options["other_group"] = open_on_jump

                sublime.active_window().run_command("dired", options)

        sublime.set_timeout(run_on_new_window, 200)
        if not ST3 and not NT:
            sublime.set_timeout(lambda: sublime.active_window().run_command("toggle_side_bar"), 200)

    def launch_ST3(self, files):
        executable_path = sublime.executable_path()
        if OSX:
            app_path = executable_path[:executable_path.rfind(".app/")+5]
            executable_path = app_path+"Contents/SharedSupport/bin/subl"
        items = [executable_path, "-n"] + files
        subprocess.Popen(items, cwd=None if NT else self.path)

    def launch_ST2(self, files):
        items = ["-n"] + files
        cwd = None if NT else self.path
        shell = False
        if NT:
            # 9200 means win8
            shell = True if sys.getwindowsversion()[2] < 9200 else False
            items = [i.encode(locale.getpreferredencoding(False)) if sys.getwindowsversion()[2] == 9200 else i for i in items]

        def app_path():
            if OSX:
                app_path = subprocess.Popen(["osascript", "-e" "tell application \"System Events\" to POSIX path of (file of process \"Sublime Text 2\" as alias)"], stdout=subprocess.PIPE).communicate()[0].rstrip()
                subl_path = "{0}/Contents/SharedSupport/bin/subl".format(app_path)
            else:
                subl_path = 'sublime_text'
            yield subl_path

        fail = False
        for c in ['subl', 'sublime', app_path()]:
            try:
                subprocess.Popen(list(c) + items, cwd=cwd, shell=shell)
            except:
                fail = True
            else:
                fail = False

        if fail:
            sublime.status_message('Cannot open a new window')


class DiredToggleAutoRefresh(TextCommand):
    def is_enabled(self):
        return self.view.score_selector(0, "text.dired") > 0

    def is_visible(self):
        return self.is_enabled()

    def description(self):
        msg = u'auto-refresh for this view'
        if self.view.settings().get('dired_autorefresh', True):
            return u'Disable ' + msg
        else:
            return u'Enable ' + msg

    def run(self, edit):
        s = self.view.settings()
        ar = s.get('dired_autorefresh', True)
        s.set('dired_autorefresh', not ar)
        self.view.run_command('dired_refresh')


class DiredPreviewDirectoryCommand(TextCommand, DiredBaseCommand):
    '''Show properties and content of directory in popup; ST3 only'''
    def run(self, edit, fqn=None, point=0):
        if not fqn:
            self.index = self.get_all()
            filenames = self.get_selected(full=True)
            if not filenames:
                return sublime.status_message(u'Nothing to preview')
            fqn = filenames[0]
            if not (isdir(fqn) or fqn == PARENT_SYM):
                return sublime.status_message(u'Something wrong')

        self.view.settings().set('dired_stop_preview_thread', False)
        self.preview_thread = threading.Thread(target=self.worker, args=(fqn if fqn != PARENT_SYM else self.get_path(),))
        self.preview_thread.start()
        width, height = self.view.viewport_extent()
        self.view.show_popup('Loading...', 0, point or self.view.sel()[0].begin(), width, height / 2, self.open_from_preview)

    def worker(self, path):
        self.preview_path = '📁 <a href="dir\v{0}">{0}</a>'.format(path)
        self.subdirs = self.files = self.size = 0
        self.errors = []
        self.open_dirs = []
        self.open_files = []
        self._created, self._accessed, self._modified = get_dates(path)

        def add_err(err): self.errors.append(str(err))

        for index, (root, dirs, files) in enumerate(os.walk(path, onerror=add_err)):
            self.subdirs += len(dirs)
            self.files += len(files)

            if not index:
                sort_nicely(dirs)
                sort_nicely(files)
                self.open_dirs = ['📁 <a href="dir\v%s%s">%s</a>' % (join(root, d), os.sep, d) for d in dirs]
                self.open_files = []

            for f in files:
                fpath = join(root, f)
                if not index:
                    self.open_files.append('≡ <a href="file\v%s">%s</a>' % (fpath, f))
                try:
                    self.size += getsize(fpath)
                except OSError as e:
                    add_err(e)

            if not self.view.is_popup_visible() or self.view.settings().get('dired_stop_preview_thread'):
                return
            sublime.set_timeout_async(self.update_preview(), 1)
        sublime.set_timeout_async(self.update_preview(loading=False), 1)

    def update_preview(self, loading=True):
        le = len(self.errors)
        if le > 5:
            if loading:
                errors = '<br>%d errors<br><br>' % le
            else:
                errors = '<br><a href="errors\v">%s errors</a> (click to view)<br><br>' % le
        else:
            errors = '<br>Errors:<br> %s<br><br>' % '<br> '.join(self.errors) if self.errors else '<br>'
        items = self.open_dirs + self.open_files
        self.view.update_popup(
            '<br>{0}{1}<br><br>'
            'Files: {2}; directories: {3}<br>'
            'Size: {4} ({5} bytes)<br><br>'
            'Created:  {6}<br>'
            'Accessed: {7}<br>'
            'Modified: {8}<br>{9}{10}'.format(
                'Loading... ' if loading else '', self.preview_path,
                self.files, self.subdirs,
                convert_size(self.size), self.size,
                self._created, self._accessed, self._modified,
                errors,
                ' %s<br><br>' % '<br> '.join(items) if items else '')
        )

    def open_from_preview(self, payload):
        msg, path = payload.split('\v')

        def show_errors(_):
            self.view.update_popup(
                '<br><a href="back\v">←<br><br>'
                '</a>Errors:<br> %s<br>' % '<br> '.join(self.errors))

        def go_back(_):
            self.update_preview(loading=False)

        def open_dir(path):
            self.view.settings().set('dired_path', path)
            self.view.run_command('dired_refresh')

        def open_file(path):
            (self.view.window() or sublime.active_window()).open_file(path)

        case = {
            'dir': open_dir,
            'file': open_file,
            'errors': show_errors,
            'back': go_back
        }
        case[msg](path)


class DiredFilePropertiesCommand(TextCommand, DiredBaseCommand):
    '''Show properties of file in popup; ST3 only'''
    def run(self, edit, fqn=None, point=0):
        if not fqn:
            self.index = self.get_all()
            filenames = self.get_selected(full=True)
            if not filenames:
                return sublime.status_message(u'Nothing to preview')

        width, height = self.view.viewport_extent()
        self.view.show_popup('Loading...', 0, point or self.view.sel()[0].begin(), width, height / 2, self.open_from_preview)
        self.get_info(fqn)

    def get_info(self, path):
        self.preview_path = path
        self.parent = dirname(path)
        self.size = 0
        self.errors = []
        self._created, self._accessed, self._modified = get_dates(path)
        try:
            self.size += getsize(path)
        except OSError as e:
            self.errors.append(str(e))
        if not self.view.is_popup_visible():
            return
        sublime.set_timeout_async(self.update_preview, 1)

    def update_preview(self):
        self.view.update_popup(
            '<br>≡ <a href="file\v{0}">{0}</a><br><br>'
            'Size: {1} ({2} bytes)<br><br>'
            'Created:  {3}<br>'
            'Accessed: {4}<br>'
            'Modified: {5}<br>'
            '{6}'
            '{7}'
            '<a href="app\v{0}">Open in default app</a><br>'
            '<a href="external\v{0}">Open parent in Finder/Explorer</a><br><br>'.format(
                self.preview_path,
                convert_size(self.size), self.size,
                self._created, self._accessed, self._modified,
                '<br>Errors:<br> %s<br><br>' % '<br> '.join(self.errors) if self.errors else '<br>',
                ('<a href="ql\v%s">Open in Quick Look</a><br>' % self.preview_path) if OSX else '')
        )

    def open_from_preview(self, payload):
        msg, path = payload.split('\v')

        def open_file(path):
            (self.view.window() or sublime.active_window()).open_file(path)

        def app(path):
            self.view.update_popup('Please, wait…')
            sublime.set_timeout_async(
                self.view.run_command('dired_quick_look', {'preview': False, 'files': [path]}), 1)

        def external(path):
            self.view.update_popup('Please, wait…')
            sublime.set_timeout_async(
                self.view.run_command('dired_open_external', {'fname': path}), 1)

        def ql(path):
            self.view.update_popup('Please, wait…')
            sublime.set_timeout_async(
                self.view.run_command('dired_quick_look', {'files': [path]}), 1)

        case = {
            'file': open_file,
            'app': app,
            'external': external,
            'ql': ql
        }
        case[msg](path)


# EVENT LISTENERS ###################################################

class DiredHoverProperties(sublime_plugin.ViewEventListener, DiredBaseCommand):
    @classmethod
    def is_applicable(cls, settings):
        return settings.get('syntax') == 'Packages/FileBrowser/dired.sublime-syntax'

    def on_hover(self, point, hover_zone):
        self.view.hide_popup()
        self.view.settings().set('dired_stop_preview_thread', True)
        if hover_zone != sublime.HOVER_GUTTER:
            return
        self.index = self.get_all()
        line = self.view.line(point)
        path = self.get_fullpath_for(line)
        self.name_point = self._get_name_point(line)
        if 'file' in self.view.scope_name(line.a):
            self.view.run_command('dired_file_properties', {'fqn': path, 'point': self.name_point})
        else:
            width, height = self.view.viewport_extent()
            self.view.show_popup('<a href="{0}">Click here to preview directory<br> {0}</a>'.format(path), 0, point or self.view.sel()[0].begin(), width, height / 2, self.open_from_preview)

    def open_from_preview(self, path):
            self.view.run_command('dired_preview_directory', {'fqn': path, 'point': self.name_point})


class DiredHijackNewWindow(EventListener):
    def on_window_command(self, window, command_name, args):
        if command_name != "new_window":
            return
        hijack_window()


class DiredHideEmptyGroup(EventListener):
    def on_close(self, view):
        if not 'dired' in view.scope_name(0):
            return
        emit_event(u'view_closed', view.id())

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
    '''Command allows to call it from other module(s)'''
    def run(self, edit, path):
        CallVCS(self.view, path)


class CallVCS(DiredBaseCommand):
    '''Magic'''
    def __init__(self, view, path):
        self.view = view
        self.vcs_state = dict(path=path)
        self.view.erase_regions('M')
        self.view.erase_regions('?')
        for vcs in ['git', 'hg']:
            self.start(vcs)
        self.watch_threads()

    def watch_threads(self):
        '''wait while all checks are done'''
        if not all(vcs in self.vcs_state for vcs in ['git', 'hg']):
            sublime.set_timeout(self.watch_threads, 100)
            return
        if 'changed_items' in self.vcs_state:
            self.vcs_colorized(self.vcs_state['changed_items'])

    def start(self, vcs):
        '''launch threads'''
        command = self.view.settings().get('%s_path' % vcs, '')
        if command:  # user can set empty string to disable integration with vcs
            vars(self)['%s_thread' % vcs] = threading.Thread(target=self.check, args=(vcs, command))
            vars(self)['%s_thread' % vcs].start()
        else:
            self.vcs_state.update({vcs: False})

    def check(self, vcs, command):
        '''target function for a thread; worker'''
        status, root = self.get_output(vcs, self.expand_command(vcs, command))
        if status and root:
            changed_items = self.vcs_state.get('changed_items', {})
            changed_items.update(dict(self.set_value(vcs, root, i) for i in status if i != ''))
            self.vcs_state.update({vcs: True, 'changed_items': changed_items})
        else:
            self.vcs_state.update({vcs: False})

    def expand_command(self, vcs, command):
        '''check if user got wildcards or envvars in custom command'''
        if any(c for c in '~*?[]$%' if c in command) and not isfile(command):
            match = glob.glob(os.path.expandvars(os.path.expanduser(command)))
            if match:
                return match[0]
            else:
                sublime.error_message(u'FileBrowser:\n'
                    u'It seems like you use wildcards in\n\n"%s_path": "%s".\n\n'
                    u'But the pattern cannot be found, please, fix it '
                    u'or use absolute path without wildcards.' % (vcs, command))
        return command

    def get_output(self, vcs, command):
        '''call a vsc, getting its output if any'''
        args = {'git_status': ['status', '--untracked-files=all', '-z'],
                'git_root':   ['rev-parse', '--show-toplevel'],
                'hg_status':  ['status'],
                'hg_root':    ['root']}
        sep = {'hg': '\n', 'git': '\x00' if ST3 else '\00'}
        status, root, shell = '', '', True if NT else False
        path = self.vcs_state['path']
        try:
            p = subprocess.Popen([command] + args['%s_status' % vcs], stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=path, shell=shell)
            status = p.communicate()[0]
            status = str(status, 'utf-8').split(sep[vcs]) if ST3 else status.split(sep[vcs])
            p = subprocess.Popen([command] + args['%s_root' % vcs], stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=path, shell=shell)
            root = p.communicate()[0].decode('utf-8').strip('\n')
        except:
            # on Windows exception is not being raised if cwd is not None and shell=True
            self.vcs_state.update({vcs: False})
        return (status, root)

    def set_value(self, vcs, root, item):
        '''return tuple (fullpath, status)'''
        item = item[1:] if vcs == 'git' else item
        filename = (item[2:] if ST3 else unicode(item[2:], 'utf-8'))
        return (join(root, filename), item[0])

    def vcs_colorized(self, changed_items):
        '''called on main thread'''
        if not self.view.settings().has('dired_index'):
            return  # view was closed
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
