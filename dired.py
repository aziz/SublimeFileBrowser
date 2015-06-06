#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import print_function
import sublime
from sublime import Region
from sublime_plugin import WindowCommand, TextCommand, EventListener
import os, re, shutil, tempfile, subprocess, itertools, sys, threading, glob
from os.path import basename, dirname, isdir, isfile, exists, join, normpath

ST3 = int(sublime.version()) >= 3000

if ST3:
    from .common import DiredBaseCommand, sort_nicely
    from . import prompt
    from .show import show
    from .show import set_proper_scheme
    from .jumping import jump_names
    MARK_OPTIONS = sublime.DRAW_NO_OUTLINE
    try:
        import Default.send2trash as send2trash
    except ImportError:
        send2trash = None
else:  # ST2 imports
    import locale
    from common import DiredBaseCommand, sort_nicely
    import prompt
    from show import show
    from show import set_proper_scheme
    from jumping import jump_names
    MARK_OPTIONS = 0
    try:
        import send2trash
    except ImportError:
        send2trash = None
PARENT_SYM = u"⠤"
OS  = sublime.platform()
NT  = OS == 'windows'
LIN = OS == 'linux'
OSX = OS == 'osx'


def print(*args, **kwargs):
    """ Redefine print() function; the reason is the inconsistent treatment of
        unicode literals among Python versions used in ST2.
        Redefining/tweaking built-in things is relatively safe; of course, when
        ST2 will become irrelevant, this def might be removed undoubtedly.
    """
    if not (ST3 or NT):
        args = (s.encode('utf-8') if isinstance(s, unicode) else str(s) for s in args)
    else:
        args = (s if isinstance(s, str if ST3 else unicode) else str(s) for s in args)
    sep, end = kwargs.get('sep', ' '), kwargs.get('end', '\n')
    sys.stdout.write(sep.join(s for s in args) + end)


def reuse_view():
    return sublime.load_settings('dired.sublime-settings').get('dired_reuse_view', False)


def hijack_window():
    settings = sublime.load_settings('dired.sublime-settings')
    command = settings.get("dired_hijack_new_window")
    if command:
        if command == "jump_list":
            sublime.set_timeout(lambda: sublime.windows()[-1].run_command("dired_jump_list"), 1)
        else:
            sublime.set_timeout(lambda: sublime.windows()[-1].run_command("dired", {"immediate": True}), 1)


def plugin_loaded():
    if len(sublime.windows()) == 1 and len(sublime.windows()[0].views()) == 0:
        hijack_window()

    window = sublime.active_window()
    if not ST3:
        global recursive_plugin_loaded
        # recursion limit is 1000 generally, so it will try to refresh for 100*1000 ms (100 s)
        # if no active_window in 100 s, then no refresh
        # if view still loading, refresh fail because view cant be edited
        if not window or any(view.is_loading() for view in window.views()):
            recursive_plugin_loaded += 1
            try:
                return sublime.set_timeout(plugin_loaded, 100)
            except RuntimeError:
                print('\ndired.plugin_loaded run recursively %d time(s); and failed to refresh\n' % recursive_plugin_loaded)
                return

    for v in window.views():
        if v.settings() and v.settings().get("dired_path"):
            # reset sels because dired_index not exists yet, so we cant restore sels
            v.run_command("dired_refresh", {"reset_sels": True})
    # if not ST3:
    #     print('\ndired.plugin_loaded run recursively %d time(s); and call refresh command\n'%recursive_plugin_loaded)

if not ST3:
    recursive_plugin_loaded = 1
    plugin_loaded()


class DiredCommand(WindowCommand):
    """
    Prompt for a directory to display and display it.
    """
    def run(self, immediate=False, single_pane=False, project=False, other_group=False):
        path, goto = self._determine_path()
        if project:
            folders = self.window.folders()
            if len(folders) == 1:
                path = folders[0]
            elif folders:
                names = [basename(f) for f in folders]
                longest_name = max([len(n) for n in names])
                for i, f in enumerate(folders):
                    name     = names[i]
                    offset   = ' ' * (longest_name - len(name) + 1)
                    names[i] = u'%s%s%s' % (name, offset, self.display_path(f))
                self.window.show_quick_panel(names, lambda i: self._show_folder(i, path, goto, single_pane, other_group), sublime.MONOSPACE_FONT)
                return
        if immediate:
            show(self.window, path, goto=goto, single_pane=single_pane, other_group=other_group)
        else:
            prompt.start('Directory:', self.window, path, self._show)

    def _show_folder(self, index, path, goto, single_pane, other_group):
        if index != -1:
            choice = self.window.folders()[index]
            if path == choice:
                show(self.window, path, goto=goto, single_pane=single_pane, other_group=other_group)
            else:
                show(self.window, choice, single_pane=single_pane, other_group=other_group)

    def _show(self, path):
        show(self.window, path)

    def _determine_path(self):
        '''Return (path, fname) so goto=fname to set cursor'''
        # Use the current view's directory if it has one.
        view = self.window.active_view()
        path = view and view.file_name()
        if path:
            return os.path.split(path)

        # Use the first project folder if there is one.
        data = self.window.project_data() if ST3 else None
        if data and 'folders' in data:
            folders = data['folders']
            if folders:
                return (folders[0]['path'], None)

        # Use window folder if possible
        folders = self.window.folders()
        if len(folders) > 0:
            return (folders[0], None)

        # Use the user's home directory.
        return (os.path.expanduser('~'), None)

    def display_path(self, folder):
        display = folder
        home = os.path.expanduser("~")
        if folder.startswith(home):
            display = folder.replace(home, "~", 1)
        return display


class DiredRefreshCommand(TextCommand, DiredBaseCommand):
    """
    Populates or repopulates a dired view.

    self.index is a representation of view lines
               list contains full path of each item in a view, except
               header ['', ''] and parent_dir [PARENT_SYM]
    self.index shall be updated according to view modifications (refresh, expand single folder, fold)
                    and stored in view settings as 'dired_index'

    The main reason for index is access speed to item path because we can
        self.index[self.view.rowcol(region.a)[0]]
    to get full path, instead of grinding with substr thru entire view
    substr is slow: https://github.com/SublimeTextIssues/Core/issues/882
    """
    def run(self, edit, goto=None, to_expand=None, toggle=None, reset_sels=None):
        """
        goto
            Optional filename to put the cursor on; used only from "dired_up"

        to_expand
            List of relative paths for direcories which shall be expanded

        toggle
            If true, marked/selected directories shall switch state,
            i.e. expand/collapse

        reset_sels
            If True, previous selections & marks shan’t be restored
        """
        # after restart ST, callback seems to disappear, so reset callback on each refresh for more reliability
        self.view.settings().clear_on_change('color_scheme')
        self.view.settings().add_on_change('color_scheme', lambda: set_proper_scheme(self.view))

        path = self.path
        self.sel = None
        expanded = self.view.find_all(u'^\s*▾') if not goto else []
        names = []
        self.number_line = 0
        self.index  = None if reset_sels else self.get_all()
        self.marked = None if reset_sels else self.get_marked()
        self.sels   = None if reset_sels else (self.get_selected(), list(self.view.sel()))

        if path == 'ThisPC\\':
            path = ''
            for s in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                disk = '%s:' % s
                if isdir(disk):
                    names.append(disk)
        if not reset_sels:
            self.re_populate_view(edit, path, names, expanded, to_expand, toggle)
        else:
            self.index = []
            if not path:
                self.continue_refreshing(edit, path, names)
            else:
                self.populate_view(edit, path, names, goto)

    def re_populate_view(self, edit, path, names, expanded, to_expand, toggle):
        root = path
        for i, r in enumerate(expanded):
            name = self.get_parent(r, path)
            expanded[i] = name.rstrip(os.sep)
        if toggle and to_expand:
            merged = list(set(expanded + to_expand))
            expanded = [e for e in merged if not (e in expanded and e in to_expand)]
        else:
            expanded.extend(to_expand or [])
        # we need prev index to setup expanded list — done, so reset index
        self.index = []
        self.show_hidden = self.view.settings().get('dired_show_hidden_files', True)
        tree = self.traverse_tree(root, root, '', names, expanded)
        if tree:
            self.set_status()
            text, header = self.set_title(path)
            if root and self.show_parent():
                text.extend(PARENT_SYM)
                self.index = [PARENT_SYM] + self.index
            if header:
                self.index = ['', ''] + self.index
            text.extend(tree)

            self.view.set_read_only(False)
            self.view.erase(edit, Region(0, self.view.size()))
            self.view.insert(edit, 0, '\n'.join(text))
            self.view.set_read_only(True)

            fileregion = self.fileregion()
            count = len(self.view.lines(fileregion)) if fileregion else 0
            self.view.settings().set('dired_count', count)
            self.view.settings().set('dired_index', self.index)

            self.restore_marks(self.marked)
            self.restore_sels(self.sels)

            CallVCS(self.view, path)
        else:
            return self.populate_view(edit, path, names, goto=None)

    def populate_view(self, edit, path, names, goto):
        if goto and goto[~0] == ':':
            goto += os.sep  # c:\\ valid path, c: not valid
        try:
            names = os.listdir(path)
        except OSError as e:
            error = str(e).split(':')[0].replace('[Error 5] ', 'Access denied')
            if not ST3 and LIN:
                error = error.decode('utf8')
            self.view.run_command("dired_up")
            self.view.set_read_only(False)
            self.view.insert(edit, self.view.line(self.view.sel()[0]).b,
                             u'\t<%s>' % error)
            self.view.set_read_only(True)
        else:
            self.continue_refreshing(edit, path, names, goto)
            CallVCS(self.view, path)

    def continue_refreshing(self, edit, path, names, goto=None):
        self.set_status()

        text, header = self.set_title(path)
        f = self.prepare_filelist(names, path, '', '')

        if path and (not f or self.show_parent()):
            text.append(PARENT_SYM)
            self.index = [PARENT_SYM] + self.index
            self.number_line += 1
        if header:
            self.index = ['', ''] + self.index
            self.number_line += 2
        text.extend(f)

        self.view.set_read_only(False)
        self.view.erase(edit, Region(0, self.view.size()))
        self.view.insert(edit, 0, '\n'.join(text))
        self.view.settings().set('dired_count', len(f))
        self.view.set_read_only(True)

        self.view.settings().set('dired_index', self.index)

        self.restore_marks(self.marked)

        # Place the cursor.
        if f:
            pt = self.fileregion(with_parent_link=True).a
            if goto:
                if isdir(join(path, goto)) and not goto.endswith(os.sep):
                    goto = u"▸ " + goto + os.sep
                else:
                    goto = u"≡ " + goto
                try:
                    line = f.index(goto) + (2 if header else 0) + (1 if self.show_parent() else 0)
                    pt = self.view.text_point(line, 2)
                    self.view.sel().clear()
                    self.view.sel().add(Region(pt, pt))
                    self.view.show_at_center(Region(pt, pt))
                except ValueError:
                    pass
            else:
                self.restore_sels(self.sels)
        else:  # empty folder?
            pt = self.view.text_point(2, 0)
            self.view.sel().clear()
            self.view.sel().add(Region(pt, pt))

    def traverse_tree(self, root, path, indent, tree, expanded):
        if not path:  # special case for ThisPC, path is empty string
            items = [u'%s\\' % d for d in tree]
            tree  = []
        else:
            # basename return funny results for c:\\ so it is tricky
            b = os.path.basename(os.path.abspath(path)) or path.rstrip(os.sep)
            if root != path and b != os.path.basename(root.rstrip(os.sep)):
                tree.append(u'%s▾ %s%s' % (indent[:-1], b.rstrip(os.sep), os.sep))
                self.index.append(u'%s%s' % (path.rstrip(os.sep), os.sep))
            try:
                if not self.show_hidden:
                    items = [name for name in os.listdir(path) if not self.is_hidden(name, path)]
                else:
                    items = os.listdir(path)
            except OSError as e:
                error = str(e).split(':')[0].replace('[Error 5] ', 'Access denied')
                if not ST3 and LIN:
                    error = error.decode('utf8')
                tree[~0] += u'\t<%s>' % error
                return
        sort_nicely(items)
        files = []
        index_files = []
        if tree and not items:
            # expanding empty folder, so notify that it is empty
            tree[~0] += '\t<empty>'
        for f in items:
            new_path = join(path, f)
            check = isdir(new_path)
            if check and new_path.replace(root, '', 1).strip(os.sep) in expanded:
                self.traverse_tree(root, new_path, indent + '\t', tree, expanded)
            elif check:
                self.index.append(u'%s%s' % (new_path.rstrip(os.sep), os.sep))
                tree.append(u'%s▸ %s%s' % (indent, f.rstrip(os.sep), os.sep))
            else:
                index_files.append(new_path)
                files.append(u'%s≡ %s' % (indent, f))
        self.index += index_files
        tree += files
        return tree

    def set_title(self, path):
        header    = self.view.settings().get('dired_header', False)
        name      = jump_names().get(path or self.path)
        caption   = u"{0} → {1}".format(name, path) if name else path or self.path
        text      = [caption, len(caption)*(u'—')] if header else []
        view_name = self.view.name()[:2]
        if not path:
            title = u'%s%s' % (view_name, name or 'This PC')
        else:
            norm_path = path.rstrip(os.sep)
            if self.view.settings().get('dired_show_full_path', False):
                title = u'%s%s (%s)' % (view_name, name or basename(norm_path), norm_path)
            else:
                title = u'%s%s' % (view_name, name or basename(norm_path))
        self.view.set_name(title)
        return (text, header)


# NAVIGATION #####################################################

class DiredNextLineCommand(TextCommand, DiredBaseCommand):
    def run(self, edit, forward=None):
        self.move(forward)


class DiredMoveCommand(TextCommand, DiredBaseCommand):
    def run(self, edit, to="bof"):
        self.move_to_extreme(to)


class DiredSelect(TextCommand, DiredBaseCommand):
    def run(self, edit, new_view=0, other_group=0, preview=0, and_close=0, inline=0, toggle=0):
        path = self.path
        self.index = self.get_all()
        if inline:
            filenames = self.get_marked() or self.get_selected(parent=False)
            if len(filenames) == 1 and filenames[0][~0] == os.sep:
                return self.expand_single_folder(edit, path, filenames[0], toggle)
            elif filenames:
                # working with several selections at once is very tricky,
                # thus for reliability we should recreate the entire tree
                # despite it is slower
                self.view.run_command('dired_refresh', {'to_expand': [f.rstrip(os.sep) for f in filenames], 'toggle': toggle})
                return
            else:
                return sublime.status_message('Item cannot be expanded')

        filenames = self.get_selected() if not (new_view or inline) else self.get_marked() or self.get_selected()

        # If reuse view is turned on and the only item is a directory, refresh the existing view.
        if not new_view and reuse_view():
            fqn = join(path, filenames[0])
            if len(filenames) == 1 and isdir(fqn):
                show(self.view.window(), fqn, view_id=self.view.id())
                return
            elif len(filenames) == 1 and filenames[0] == PARENT_SYM:
                self.view.window().run_command("dired_up")
                return

        w = self.view.window()
        if other_group or preview or and_close:
            dired_view = self.view
            nag = self.view.window().active_group()
            if not and_close:
                target_group = self._other_group(w, nag)
                # set_view_index and focus are not very reliable
                # just focus target_group should do what we want
                w.focus_group(target_group)

        for filename in filenames:
            fqn = join(path, filename)
            if exists(fqn):  # ignore 'item <error>'
                if isdir(fqn):
                    show(w, fqn, ignore_existing=new_view)
                else:
                    if preview:
                        w.open_file(fqn, sublime.TRANSIENT)
                        w.focus_view(dired_view)
                        return  # preview is possible for a single file only
                    else:
                        v = w.open_file(fqn)
        if and_close:
            w.focus_view(dired_view)
            w.run_command("close")
            w.focus_view(v)

    def _other_group(self, w, nag):
        '''
        creates new group if need and return index of the group where files
        shall be opened
        '''
        groups = w.num_groups()
        if groups == 1:
            w.set_layout({"cols": [0.0, 0.3, 1.0], "rows": [0.0, 1.0], "cells": [[0, 0, 1, 1], [1, 0, 2, 1]]})
        if groups <= 4 and nag < 2:
            group = 1 if nag == 0 else 0
        elif groups == 4 and nag >= 2:
            group = 3 if nag == 2 else 2
        else:
            group = nag - 1
        return group

    def expand_single_folder(self, edit, path, filename, toggle):
        marked = self.get_marked()
        sels   = self.get_selected()

        if toggle:
            line = self.view.line(self.view.get_regions('marked')[0] if marked else
                                  list(self.view.sel())[0])
            content = self.view.substr(line).lstrip()[0]
            if content == u'▾':
                self.view.run_command('dired_fold')
                return

        self.view.run_command('dired_fold', {'update': True, 'index': self.index})
        self.index = self.get_all()  # fold changed index, get a new one
        sel  = self.view.get_regions('marked')[0] if marked else list(self.view.sel())[0]
        line = self.view.line(sel)
        # bah, 0-based index sucks, have to take number of next line to make slicing work properly
        self.number_line = 1 + self.view.rowcol(line.a)[0]
        fqn  = join(path, filename)
        if isdir(fqn):
            self.sel = sel
            try:
                names = os.listdir(fqn)
            except OSError as e:
                error = str(e).split(':')[0].replace('[Error 5] ', 'Access denied')
                if not ST3 and LIN:
                    error = error.decode('utf8')
                replacement = u'%s\t<%s>' % (self.view.substr(line), error)
            else:
                path = self.path if self.path != 'ThisPC\\' else ''
                replacement = self.prepare_treeview(names, path, fqn, '\t')
        else:
            replacement = '%s\t<%s>' % (self.view.substr(line), 'Not exists, press r to refresh')
        self.view.set_read_only(False)
        self.view.replace(edit, line, replacement)
        self.view.set_read_only(True)
        self.view.settings().set('dired_index', self.index)
        self.restore_marks(marked)
        self.restore_sels((sels, [sel]))
        CallVCS(self.view, path)


class DiredFold(TextCommand, DiredBaseCommand):
    u'''
    This command used to fold/erase/shrink (whatever you like to call it) content
    of some [sub]directory (within current directory, see self.path).
    There are two cases when this command would be fired:
        1. User mean to fold   (key ←)
        2. User mean to unfold (key →)
    In first case we just erase region and set dired_count; however, we need to
    figure out which region to erase:
        (a) if cursor placed on directory item and next line indented
            (representing content of the directory) — erase indented line;
        (b) next line is not indented, but the line of directory item is indented —
            erase directory item itself;
        (c) cursor placed on file item which is indented — erase file item.
    In second case we need to decide if erasing needed or not:
        (a) if directory was unfolded (as in 1.a) — erase that region, so then
            it’ll be filled (basically it is like update/refresh), also set dired_count;
        (b) directory was folded (as in 1.b) — do nothing
    '''
    def run(self, edit, update=None, index=None):
        v = self.view
        self.index  = index or self.get_all()
        self.marked = None
        self.seled  = (self.get_selected(), list(self.view.sel()))
        marks       = self.view.get_regions('marked')
        virt_sels   = []

        if marks:
            for m in marks:
                if 'directory' in self.view.scope_name(m.a):
                    virt_sels.append(Region(m.a, m.a))
            self.marked = self.get_marked()
        sels = virt_sels

        lines = [v.line(s.a) for s in reversed(sels or list(v.sel()))]
        for line in lines:
            self.fold(edit, v, line, update)
        if self.marked:
            self.restore_marks(self.marked)
        if self.seled:
            self.restore_sels(self.seled)

    def fold(self, edit, v, line, update):
        current_region = v.indented_region(line.b)
        next_region    = v.indented_region(line.b + 2)
        is_folder      = 'directory' in v.scope_name(line.a)
        folded_subfolder = update and (next_region.contains(line) or next_region.empty() or next_region.contains(current_region))
        folded_folder    = update and current_region.empty() and next_region.empty()
        file_item_in_root = not is_folder and current_region.empty()

        if 'error' in v.scope_name(line.b - 1):
            # remove inline errors, e.g. <empty>
            indented_region = v.extract_scope(line.b - 1)
        elif folded_subfolder or folded_folder or file_item_in_root:
            return  # folding is not supposed to happen, so we exit
        elif update or (is_folder and not next_region.empty() and not next_region.contains(line)):
            indented_region = next_region
        elif not current_region.empty():
            indented_region = current_region
            line = v.line(indented_region.a - 2)
        else:
            return  # this is not supposed to happen, but it does sometimes
        name_point  = v.extract_scope(line.a).b
        if 'name' in v.scope_name(name_point):
            icon_region = Region(name_point - 2, name_point - 1)
        else:
            icon_region = Region(line.a, line.a + 1)

        # do not set count & index on empty folder
        if not line.contains(indented_region):
            dired_count = v.settings().get('dired_count', 0)
            v.settings().set('dired_count', int(dired_count) - len(v.lines(indented_region)))
            if indented_region.b == v.size():
                # MUST avoid new line at eof
                indented_region = Region(indented_region.a - 1, indented_region.b)

            line_number = 1 + v.rowcol(line.a)[0]
            removed_lines = line_number + len(v.lines(indented_region))
            v.settings().set('dired_index', self.index[:line_number] + self.index[removed_lines:])

        if self.marked or self.seled:
            path = self.path
            folded_name = self.get_parent(line, path)
            if self.marked:
                self.marked.append(folded_name)
            elif self.seled:
                self.seled[0].append(folded_name)

        v.set_read_only(False)
        v.replace(edit, icon_region, u'▸')
        v.erase(edit, indented_region)
        v.set_read_only(True)


class DiredUpCommand(TextCommand, DiredBaseCommand):
    def run(self, edit):
        path = self.path
        parent = dirname(path.rstrip(os.sep))
        if parent != os.sep and parent[1:] != ':\\':
            # need to avoid c:\\\\
            parent += os.sep
        if parent == path and NT:
            parent = 'ThisPC'
        elif parent == path:
            return
        elif path == 'ThisPC\\':
            self.view.run_command('dired_refresh')
            return

        view_id = (self.view.id() if reuse_view() else None)
        show(self.view.window(), parent, view_id, goto=basename(path.rstrip(os.sep)))


class DiredGotoCommand(TextCommand, DiredBaseCommand):
    """
    Prompt for a new directory.
    """
    def run(self, edit):
        prompt.start('Goto:', self.view.window(), self.path, self.goto)

    def goto(self, path):
        show(self.view.window(), path, view_id=self.view.id())


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


# MARKING ###########################################################

class DiredMarkExtensionCommand(TextCommand, DiredBaseCommand):
    def run(self, edit):
        filergn = self.fileregion()
        if filergn.empty():
            return
        current_item = self.view.substr(self.view.line(self.view.sel()[0].a))
        if current_item.endswith(os.sep) or current_item == PARENT_SYM:
            ext = ''
        else:
            ext = current_item.split('.')[-1]
        pv = self.view.window().show_input_panel('Extension:', ext, self.on_done, None, None)
        pv.run_command("select_all")

    def on_done(self, ext):
        ext = ext.strip()
        if not ext:
            return
        if not ext.startswith('.'):
            ext = '.' + ext
        self._mark(mark=lambda oldmark, filename: filename.endswith(ext) and True or oldmark,
                   regions=self.fileregion())


class DiredMarkCommand(TextCommand, DiredBaseCommand):
    """
    Marks or unmarks files.

    The mark can be set to '*' to mark a file, ' ' to unmark a file,  or 't' to toggle the
    mark.

    By default only selected files are marked, but if markall is True all files are
    marked/unmarked and the selection is ignored.

    If there is no selection and mark is '*', the cursor is moved to the next line so
    successive files can be marked by repeating the mark key binding (e.g. 'm').
    """
    def run(self, edit, mark=True, markall=False, forward=True):
        assert mark in (True, False, 'toggle')

        filergn = self.fileregion()
        if filergn.empty():
            return

        if not mark and markall:
            self.view.erase_regions('marked')
            return

        # If markall is set, mark/unmark all files.  Otherwise only those that are selected.
        regions = [filergn] if markall else self.view.sel()

        if mark == 'toggle':
            mark = lambda oldmark, filename: not oldmark

        self._mark(mark=mark, regions=regions)

        # If there is no selection, move the cursor forward so the user can keep pressing 'm'
        # to mark successive files.
        if not markall and len(self.view.sel()) == 1 and self.view.sel()[0].empty():
            self.move(forward)


# MANIPULATION ######################################################

class DiredCreateCommand(TextCommand, DiredBaseCommand):
    def run(self, edit, which=None):
        assert which in ('file', 'directory'), "which: " + which
        self.index = self.get_all()
        relative_path = self.get_selected(parent=False) or ""
        if relative_path:
            relative_path = relative_path[0]
            if relative_path[~0] != os.sep:
                relative_path = os.path.split(relative_path)[0] + os.sep
            if relative_path == os.sep:
                relative_path = ""

        # Is there a better way to do this?  Why isn't there some kind of context?  I assume
        # the command instance is global and really shouldn't have instance information.
        callback = getattr(self, 'on_done_' + which, None)
        pv = self.view.window().show_input_panel(which.capitalize() + ':', relative_path, callback, None, None)
        pv.run_command('move_to', {'to': 'eol', 'extend': False})

    def on_done_file(self, value):
        self._on_done('file', value)

    def on_done_directory(self, value):
        self._on_done('directory', value)

    def _on_done(self, which, value):
        value = value.strip()
        if not value:
            return

        fqn = join(self.path, value)
        if exists(fqn):
            sublime.error_message(u'{0} already exists'.format(fqn))
            return

        if which == 'directory':
            os.makedirs(fqn)
        else:
            with open(fqn, 'wb'):
                pass

        self.view.run_command('dired_refresh')


class DiredDeleteCommand(TextCommand, DiredBaseCommand):
    def run(self, edit, trash=False):
        self.index = self.get_all()
        files = self.get_marked() or self.get_selected(parent=False)
        if files:
            # Yes, I know this is English.  Not sure how Sublime is translating.
            if len(files) == 1:
                msg = u"Delete {0}?".format(files[0])
            else:
                msg = u"Delete {0} items?".format(len(files))
            if trash:
                need_confirm = self.view.settings().get('dired_confirm_send2trash')
            if trash and not send2trash:
                msg = u"Cannot delete to trash.\nPermanently " + msg.replace('D', 'd', 1)
                trash = False
            elif trash and need_confirm:
                msg = msg.replace('Delete', 'Delete to trash', 1)

            if trash and send2trash:
                if not need_confirm or (need_confirm and sublime.ok_cancel_dialog(msg)):
                    self._to_trash(files)
            elif not trash and sublime.ok_cancel_dialog(msg):
                self._delete(files)
            else:
                print("Cancel delete or something wrong in DiredDeleteCommand")

    def _to_trash(self, files):
        path = self.path
        errors = []

        def _status(filename='', done=False):
            if done:
                sublime.set_timeout(lambda: self.view.run_command('dired_refresh'), 1)
                if errors:
                    sublime.error_message(u'Some files couldn’t be sent to trash (perhaps, they are being used by another process): \n\n'
                                          + '\n'.join(errors).replace('Couldn\'t perform operation.', ''))
            else:
                status = u'Please, wait… Removing ' + filename
                sublime.set_timeout(lambda: self.view.set_status("__FileBrowser__", status), 1)

        def _sender(files, event_for_wait, event_for_set):
            for filename in files:
                event_for_wait.wait()
                event_for_wait.clear()
                if event_for_wait is remove_event:
                    try:
                        send2trash.send2trash(join(path, filename))
                    except OSError as e:
                        errors.append(u'{0}:\t{1}'.format(e, filename))
                else:
                    _status(filename)
                event_for_set.set()
            if event_for_wait is remove_event:
                _status(done=True)

        remove_event = threading.Event()
        report_event = threading.Event()
        t1 = threading.Thread(target=_sender, args=(files, remove_event, report_event))
        t2 = threading.Thread(target=_sender, args=(files, report_event, remove_event))
        t1.start()
        t2.start()
        report_event.set()

    def _delete(self, files):
        errors = []
        if ST3:
            fail = (PermissionError, FileNotFoundError)
        else:
            fail = OSError
            sys_enc = locale.getpreferredencoding(False)
        for filename in files:
            fqn = join(self.path, filename)
            try:
                if isdir(fqn):
                    shutil.rmtree(fqn)
                else:
                    os.remove(fqn)
            except fail as e:
                e = str(e).split(':')[0].replace('[Error 5] ', 'Access denied')
                if not ST3:
                    try:
                        e = str(e).decode(sys_enc)
                    except:  # failed getpreferredencoding
                        e = 'Unknown error'
                errors.append(u'{0}:\t{1}'.format(e, filename))
        self.view.run_command('dired_refresh')
        if errors:
            sublime.error_message(u'Some files couldn’t be deleted: \n\n' + '\n'.join(errors))


class DiredRenameCommand(TextCommand, DiredBaseCommand):
    def run(self, edit):
        if self.filecount():
            # Store the original filenames so we can compare later.
            path = self.path
            self.view.settings().set('rename', self.get_all_relative(path))
            self.view.settings().set('dired_rename_mode', True)
            self.view.set_read_only(False)

            self.set_ui_in_rename_mode(edit)

            self.view.set_status("__FileBrowser__", u" 𝌆 [enter: Apply changes] [escape: Discard changes] %s" % (u'¡¡¡DO NOT RENAME DISKS!!! you can rename their children though ' if self.path == 'ThisPC\\' else ''))

            # Mark the original filename lines so we can make sure they are in the same
            # place.
            r = self.fileregion()
            self.view.add_regions('rename', [r], '', '', MARK_OPTIONS)


class DiredRenameCancelCommand(TextCommand, DiredBaseCommand):
    """
    Cancel rename mode.
    """
    def run(self, edit):
        self.view.settings().erase('rename')
        self.view.settings().set('dired_rename_mode', False)
        self.view.run_command('dired_refresh')


class DiredRenameCommitCommand(TextCommand, DiredBaseCommand):
    def run(self, edit):
        if not self.view.settings().has('rename'):
            # Shouldn't happen, but we want to cleanup when things go wrong.
            self.view.run_command('dired_refresh')
            return

        before = self.view.settings().get('rename')

        # We marked the set of files with a region.  Make sure the region still has the same
        # number of files.
        after = []

        self.index = self.get_all()
        path = self.path
        for region in self.view.get_regions('rename'):
            for line in self.view.lines(region):
                parent = dirname(self.get_parent(line, path).rstrip(os.sep))
                name = self.view.substr(Region(self._get_name_point(line), line.b))
                after.append(join(parent, name))

        if len(after) != len(before):
            sublime.error_message('You cannot add or remove lines')
            return

        if len(set(after)) != len(after):
            sublime.error_message('There are duplicate filenames (see details in console)')
            self.view.window().run_command("show_panel", {"panel": "console"})
            print(*(u'\n   Original name: {0}\nConflicting name: {1}'.format(b, a)
                    for (b, a) in zip(before, after) if b != a and a in before),
                  sep='\n', end='\n\n')
            print('You can either resolve conflicts and apply changes or cancel renaming.\n')
            return

        diffs = [(b, a) for (b, a) in zip(before, after) if b != a]
        if diffs:
            existing = set(before)
            while diffs:
                b, a = diffs.pop(0)

                if a in existing:
                    # There is already a file with this name.  Give it a temporary name (in
                    # case of cycles like "x->z and z->x") and put it back on the list.
                    tmp = tempfile.NamedTemporaryFile(delete=False, dir=self.path).name
                    os.unlink(tmp)
                    diffs.append((tmp, a))
                    a = tmp

                print(u'dired rename: {0} → {1}'.format(b, a))
                orig = join(self.path, b)
                if orig[~0] == '/' and os.path.islink(orig[:~0]):
                    # last slash shall be omitted; file has no last slash,
                    # thus it False and symlink to file shall be os.rename'd
                    dest = os.readlink(orig[:~0])
                    os.unlink(orig[:~0])
                    os.symlink(dest, join(self.path, a)[:~0])
                else:
                    try:
                        os.rename(orig, join(self.path, a))
                    except OSError:
                        msg = (u'FileBrowser:\n\nError is occured during renaming.\n'
                               u'Please, fix it and apply changes or cancel renaming.\n\n'
                               u'\t {0} → {1}\n\n'
                               u'Don’t rename\n'
                               u'  • parent and child at the same time\n'
                               u'  • non-existed file (cancel renaming to refresh)\n'
                               u'  • file if you’re not owner'
                               u'  • disk letter on Windows\n'.format(b, a))
                        sublime.error_message(msg)
                        return
                existing.remove(b)
                existing.add(a)

        self.view.erase_regions('rename')
        self.view.settings().erase('rename')
        self.view.settings().set('dired_rename_mode', False)
        self.view.run_command('dired_refresh')


class DiredCopyFilesCommand(TextCommand, DiredBaseCommand):
    def run(self, edit, cut=False):
        self.index = self.get_all()
        path      = self.path if self.path != 'ThisPC\\' else ''
        filenames = self.get_marked() or self.get_selected(parent=False)
        if not filenames:
            return sublime.status_message('Nothing chosen')
        settings  = sublime.load_settings('dired.sublime-settings')
        copy_list = settings.get('dired_to_copy', [])
        cut_list  = settings.get('dired_to_move', [])
        # copied item shall not be added into cut list, and vice versa
        for f in filenames:
            full_fn = join(path, f)
            if cut:
                if not full_fn in copy_list:
                    cut_list.append(full_fn)
            else:
                if not full_fn in cut_list:
                    copy_list.append(full_fn)
        settings.set('dired_to_move', list(set(cut_list)))
        settings.set('dired_to_copy', list(set(copy_list)))
        sublime.save_settings('dired.sublime-settings')
        self.set_status()


class DiredPasteFilesCommand(TextCommand, DiredBaseCommand):
    def run(self, edit):
        s = self.view.settings()
        sources_move = s.get('dired_to_move', [])
        sources_copy = s.get('dired_to_copy', [])
        if not (sources_move or sources_copy):
            return sublime.status_message('Nothing to paste')

        self.index = self.get_all()
        path = self.path if self.path != 'ThisPC\\' else ''
        relative_path = self.get_selected(parent=False) or ''
        if relative_path:
            relative_path = relative_path[0]
            if relative_path[~0] != os.sep:
                relative_path = os.path.split(relative_path)[0] + os.sep
            if relative_path == os.sep:
                relative_path = ""
        destination = join(path, relative_path) or path
        if NT:
            return call_SHFileOperationW(self.view, sources_move, sources_copy, destination)
        else:
            return call_SystemAgnosticFileOperation(self.view, sources_move, sources_copy, destination)


class DiredClearCopyCutList(TextCommand):
    def run(self, edit):
        sublime.load_settings('dired.sublime-settings').set('dired_to_move', [])
        sublime.load_settings('dired.sublime-settings').set('dired_to_copy', [])
        sublime.save_settings('dired.sublime-settings')
        self.view.run_command('dired_refresh')


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

class DiredToggleHiddenFilesCommand(TextCommand):
    def run(self, edit):
        show = self.view.settings().get('dired_show_hidden_files', True)
        self.view.settings().set('dired_show_hidden_files', not show)
        self.view.run_command('dired_refresh')


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
    """
    open dir/file in external file explorer
    """
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


# MOUSE INTERATIONS #################################################

def dired_mouse_arguments(sel):
    if 'directory' in sel:
        return {"inline": True, "toggle": True}
    else:
        return {"other_group": True}

if ST3:
    class DiredDoubleclickCommand(TextCommand, DiredBaseCommand):
        def run_(self, view, args):
            s = self.view.settings()
            if s.get("dired_path") and not s.get("dired_rename_mode"):
                self.view.run_command("dired_select", dired_mouse_arguments(self.view.scope_name(self.view.sel()[0].a)))
            else:
                system_command = args["command"] if "command" in args else None
                if system_command:
                    system_args = dict({"event": args["event"]}.items())
                    system_args.update(dict(args["args"].items()))
                    self.view.run_command(system_command, system_args)
else:
    class DiredDoubleclickCommand(TextCommand, DiredBaseCommand):
        def run_(self, args):
            s = self.view.settings()
            if s.get("dired_path") and not s.get("dired_rename_mode"):
                self.view.run_command("dired_select", dired_mouse_arguments(self.view.scope_name(self.view.sel()[0].a)))
            else:
                system_command = args["command"] if "command" in args else None
                if system_command:
                    system_args = dict({"event": args["event"]}.items())
                    system_args.update(dict(args["args"].items()))
                    self.view.run_command(system_command, system_args)


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
        self.watch_threads()

    def watch_threads(self):
        if not 'git' in self.vcs_state:
            sublime.set_timeout(self.watch_threads, 100)
            return
        if 'changed_items' in self.vcs_state:
            self.vcs_colorized(self.vcs_state['changed_items'])

    def call_git(self, path):
        git = self.view.settings().get('git_path', '')
        if git:  # empty string disable git integration
            self.vcs_thread = threading.Thread(target=self.vcs_check, args=(path, git))
            self.vcs_thread.start()
        else:
            self.vcs_state.update(git=False)

    def vcs_check(self, path, git='git'):
        if any(c for c in '~*?[]' if c in git):
            match = glob.glob(os.path.expanduser(git))
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

    def vcs_colorized(self, changed_items):
        modified, untracked = [], []
        files_regions = dict((f, r) for f, r in zip(self.get_all(), self.view.split_by_newlines(self.fileregion())))
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


class call_SHFileOperationW(object):
    '''call Windows API for file operations'''
    def __init__(self, view, sources_move, sources_copy, destination):
        self.view = view
        if sources_move:
            self.shfow_m_thread = threading.Thread(target=self.caller, args=(1, sources_move, destination))
            self.shfow_m_thread.start()
        if sources_copy:
            # if user paste files in the same folder where they are then
            # it shall duplicate these files w/o asking anything
            dups = [p for p in sources_copy if os.path.split(p.rstrip(os.sep))[0] == destination.rstrip(os.sep)]
            if dups:
                self.shfow_d_thread = threading.Thread(target=self.caller, args=(2, dups, destination, True))
                self.shfow_d_thread.start()
                sources_copy = [p for p in sources_copy if p not in dups]
                if sources_copy:
                    self.shfow_c_thread = threading.Thread(target=self.caller, args=(2, sources_copy, destination))
                    self.shfow_c_thread.start()
            else:
                self.shfow_c_thread = threading.Thread(target=self.caller, args=(2, sources_copy, destination))
                self.shfow_c_thread.start()

    def caller(self, mode, sources, destination, duplicate=False):
        '''mode is int either 1 (move) or 2 (copy)'''
        import ctypes
        if ST3: from Default.send2trash.plat_win import SHFILEOPSTRUCTW
        else:   from send2trash.plat_win import SHFILEOPSTRUCTW

        fFlags = 8 if duplicate else 0
        SHFileOperationW = ctypes.windll.shell32.SHFileOperationW
        SHFileOperationW.argtypes = [ctypes.POINTER(SHFILEOPSTRUCTW)]
        pFrom = u'\x00'.join(sources) + u'\x00'
        pTo   = u'%s\x00' % destination
        args  = SHFILEOPSTRUCTW(wFunc  = ctypes.wintypes.UINT(mode),
                                pFrom  = ctypes.wintypes.LPCWSTR(pFrom),
                                pTo    = ctypes.wintypes.LPCWSTR(pTo),
                                fFlags = fFlags,
                                fAnyOperationsAborted = ctypes.wintypes.BOOL())
        out = SHFileOperationW(ctypes.byref(args))
        if not out:  # 0 == success
            sublime.set_timeout(lambda: self.view.run_command('dired_clear_copy_cut_list'), 1)
        else:  # probably user cancel op., or sth went wrong; keep settings
            sublime.set_timeout(lambda: self.view.run_command('dired_refresh'), 1)


class call_SystemAgnosticFileOperation(object):
    '''file operations using Python standard library'''
    def __init__(self, view, sources_move, sources_copy, destination):
        self.view    = view
        self.window  = view.window()
        self.threads = []
        self.errors  = {}

        if sources_move:
            self.caller('move', sources_move, destination)
        if sources_copy:
            # if user paste files in the same folder where they are then
            # it shall duplicate these files w/o asking anything
            dups = [p for p in sources_copy if os.path.split(p.rstrip(os.sep))[0] == destination.rstrip(os.sep)]
            if dups:
                self.caller('copy', dups, destination, duplicate=True)
                sources_copy = [p for p in sources_copy if p not in dups]
                if sources_copy:
                    self.caller('copy', sources_copy, destination)
            else:
                self.caller('copy', sources_copy, destination)

        msg = u'FileBrowser:\n\nSome files exist already, Cancel to skip all, OK to overwrite or rename.\n\n\t%s' % '\n\t'.join(self.errors.keys())
        if self.errors and sublime.ok_cancel_dialog(msg):
            t, f = self.errors.popitem()
            self.actions = [['Overwrite', 'Folder cannot be overwritten'],
                            ['Duplicate', 'Item will be renamed automatically']]
            self.show_quick_panel(self.actions + [[u'from %s' % f, 'Skip'], [u'to   %s' % t, 'Skip']],
                                  lambda i: self.user_input(i, f, t))
        self.start_threads()

    def start_threads(self):
        if self.threads:
            for t in self.threads:
                t.start()
            self.progress_bar(self.threads)

    def show_quick_panel(self, options, done):
        sublime.set_timeout(lambda: self.window.show_quick_panel(options, done, sublime.MONOSPACE_FONT), 10)
        return

    def user_input(self, i, name, new_name):
        if i == 0:
            self._setup_dir_or_file('copy', name, new_name, overwrite=True)
        if i == 1:
            self._setup_dir_or_file('copy', name, new_name, duplicate=True)
        if self.errors:
            t, f = self.errors.popitem()
            self.show_quick_panel(self.actions + [[u'from %s' % f, 'Skip'], [u'to   %s' % t, 'Skip']],
                                  lambda i: self.user_input(i, f, t))
        else:
            self.start_threads()

    def caller(self, mode, sources, destination, duplicate=False, overwrite=False):
        for fqn in sources:
            new_name = join(destination, basename(fqn.rstrip(os.sep)))
            self._setup_dir_or_file(mode, fqn, new_name, duplicate, overwrite)

    def _setup_dir_or_file(self, mode, fqn, new_name, duplicate=False, overwrite=False):
        if duplicate:
            new_name = self.generic_nn(new_name)
        if mode == 'move':
            if fqn != dirname(new_name):
                if not exists(new_name):
                    self._init_thread('move', fqn, new_name)
                else:
                    self.errors.update({str(new_name): fqn})
        if mode == 'copy':
            if isdir(fqn):
                if not isdir(new_name) or overwrite:
                    self._init_thread('dir', fqn, new_name)
                else:
                    self.errors.update({str(new_name): fqn})
            else:
                if not isfile(new_name) or overwrite:
                    self._init_thread('file', fqn, new_name)
                else:
                    self.errors.update({str(new_name): fqn})

    def _init_thread(self, mode, source_name, new_name):
        t = threading.Thread(target=self._do, args=(mode, source_name, new_name))
        t.setName(new_name if ST3 else new_name.encode('utf8'))
        self.threads.append(t)

    def _do(self, mode, source_name, new_name):
        try:
            if mode == 'move': shutil.move(source_name, new_name)
            if mode == 'dir':  shutil.copytree(source_name, new_name)
            if mode == 'file': shutil.copy2(source_name, new_name)
        except shutil.Error as e:
            m = e.args[0]
            if isinstance(m, list):
                sublime.error_message(u'FileBrowser:\n\n%s' % u'\n'.join([i[~0] for i in m]))
            else:
                sublime.error_message(u'FileBrowser:\n\n%s' % e)
        except Exception as e:  # just in case
            sublime.error_message(u'FileBrowser:\n\n%s' % str([e]))

    def progress_bar(self, threads, i=0, dir=1):
        threads = [t for t in threads if t.is_alive()]
        if threads:
            # This animates a little activity indicator in the status area
            before = i % 8
            after = (7) - before
            if not after:  dir = -1
            if not before: dir = 1
            i += dir
            self.view.set_status('__FileBrowser__', u'Please wait%s…%sWriting %s' %
                                 (' ' * before, ' ' * after, u', '.join([t.name if ST3 else t.name.decode('utf8') for t in threads])))
            sublime.set_timeout(lambda: self.progress_bar(threads, i, dir), 100)
            return
        else:
            self.view.run_command('dired_clear_copy_cut_list')

    def generic_nn(self, new_name):
        for i in itertools.count(2):
            path, name = os.path.split(new_name)
            split_name = name.split('.')
            if len(split_name) == 1 or isdir(new_name):
                cfp = u"{1} — {0}".format(i, new_name)
            else:
                # leading space may cause problems, e.g.
                # good: 'name — 2.ext'
                # good: '— 2.ext'
                # bad:  ' — 2.ext'
                fn  = '.'.join(split_name[:~0])
                new = (u'%s ' % fn) if fn else ''
                cfp = u"{1}— {0}.{2}".format(i, join(path, new), split_name[~0])
            if not os.path.exists(cfp):
                break
        return cfp
