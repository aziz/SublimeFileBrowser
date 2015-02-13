#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import print_function
import sublime
from sublime import Region
from sublime_plugin import WindowCommand, TextCommand, EventListener
import os, re, shutil, tempfile, subprocess, itertools, sys, threading, glob, fnmatch
from os.path import basename, dirname, isdir, isfile, exists, join, isabs, normpath, normcase

if sublime.platform() == 'windows':
    import ctypes

ST3 = int(sublime.version()) >= 3000

if ST3:
    from .common import RE_FILE, DiredBaseCommand
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
    from common import RE_FILE, DiredBaseCommand
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


def print(*args, **kwargs):
    """ Redefine print() function; the reason is the inconsistent treatment of
        unicode literals among Python versions used in ST2.
        Redefining/tweaking built-in things is relatively safe; of course, when
        ST2 will become irrelevant, this def might be removed undoubtedly.
    """
    if not ST3 and sublime.platform() != 'windows':
        args = (s.encode('utf-8') if isinstance(s, unicode) else str(s) for s in args)
    else:
        args = (s if isinstance(s, str if ST3 else unicode) else str(s) for s in args)
    sep, end = kwargs.get('sep', ' '), kwargs.get('end', '\n')
    sys.stdout.write(sep.join(s for s in args) + end)


def reuse_view():
    return sublime.load_settings('dired.sublime-settings').get('dired_reuse_view', False)


def sort_nicely(l):
    """ Sort the given list in the way that humans expect.
    Source: http://www.codinghorror.com/blog/2007/12/sorting-for-humans-natural-sort-order.html
    """
    convert = lambda text: int(text) if text.isdigit() else text.lower()
    alphanum_key = lambda key: [convert(c) for c in re.split('([0-9]+)', key)]
    l.sort(key=alphanum_key)


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
                print('\ndired.plugin_loaded run recursively %d time(s); and failed to refresh\n'%recursive_plugin_loaded)
                return

    for v in window.views():
        if v.settings() and v.settings().get("dired_path"):
            v.run_command("dired_refresh")
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
                folders = [ [basename(f), f] for f in folders]
                self.window.show_quick_panel(folders, lambda i: self._show_folder(i, path, goto, single_pane, other_group))
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


class DiredRefreshCommand(TextCommand, DiredBaseCommand):
    """
    Populates or repopulates a dired view.
    """
    def run(self, edit, goto=None, inline=False):
        """
        goto
            Optional filename to put the cursor on.
        """
        path = self.path
        try:
            names = os.listdir(path if not inline else goto)
        except OSError as e:
            if not inline:
                self.view.run_command("dired_up")
            self.view.set_read_only(False)
            self.view.insert(edit, self.view.line(self.view.sel()[0]).b,
                             '\t<%s>' % str(e).split(':')[0]
                             .replace('[Error 5] ', 'Access denied'))
            self.view.set_read_only(True)
        else:
            git = self.view.settings().get('git_path', '')
            if git:  # empty string disable git integration
                self.vcs_thread = threading.Thread(target=self.vcs_check, args=(edit, path, names, git))
                self.vcs_thread.start()
            self.continue_refreshing(edit, path, names, goto, indent='\t' if inline else '')

    def continue_refreshing(self, edit, path, names, goto=None, indent=''):
        status = u" 𝌆 [?: Help] "
        # if view isnot focused, view.window() may be None
        window = self.view.window() or sublime.active_window()
        path_in_project = any(folder == self.path[:-1] for folder in window.folders())
        status += 'Project root, ' if path_in_project else ''
        show_hidden = self.view.settings().get('dired_show_hidden_files', True)
        status += 'Hidden: On' if show_hidden else 'Hidden: Off'
        self.view.set_status("__FileBrowser__", status)

        if not show_hidden:
            names = [name for name in names if not self.is_hidden(name)]
        sort_nicely(names)

        f = self.ls(path, names, goto=goto if indent else '', indent=indent)

        marked = set(self.get_marked())

        self.view.set_read_only(False)

        if indent:
            line = self.view.line(self.view.sel()[0])
            name_point = self.view.extract_scope(line.b - 1).a
        if indent and f:
            icon_region = Region(name_point - 2, name_point - 1)
            self.view.replace(edit, icon_region, u'▾')
            self.view.insert(edit, line.b, '\n'+'\n'.join(f))
            dired_count = self.view.settings().get('dired_count', 0)
            self.view.settings().set('dired_count', int(dired_count) + len(f))
        elif indent:
            self.view.insert(edit, self.view.line(self.view.sel()[0]).b, '\t<empty>')
        else:
            header    = self.view.settings().get('dired_header', False)
            name      = jump_names().get(path or self.path)
            caption   = u"{0} → {1}".format(name, path) if name else path
            text      = [ caption, len(caption)*(u'—') ] if header else []
            view_name = self.view.name()[:2]
            norm_path = path.rstrip(os.sep)
            if self.view.settings().get('dired_show_full_path', False):
                title = u'%s%s (%s)' % (view_name, name or basename(norm_path), norm_path)
            else:
                title = u'%s%s' % (view_name, name or basename(norm_path))
            self.view.set_name(title)
            if not f or self.show_parent():
                text.append(PARENT_SYM)
            text.extend(f)

            self.view.erase(edit, Region(0, self.view.size()))
            self.view.insert(edit, 0, '\n'.join(text))
            self.view.settings().set('dired_count', len(f))

        if marked:
            # Even if we have the same filenames, they may have moved so we have to manually
            # find them again.
            regions = []
            for line in self.view.lines(self.fileregion()):
                filename = self._remove_ui(RE_FILE.match(self.view.substr(line)).group(1))
                if filename in marked:
                    name_region = Region(line.a + 2, line.b) # do not mark UI elements
                    regions.append(name_region)
            self.view.add_regions('marked', regions, 'dired.marked', '', MARK_OPTIONS)
        else:
            self.view.erase_regions('marked')

        self.view.set_read_only(True)

        # Place the cursor.
        if f and not indent:
            pt = self.fileregion(with_parent_link=True).a
            if goto:
                if isdir(join(path, goto)) and not goto.endswith(os.sep):
                    goto = u"▸ " + goto + os.sep
                else:
                    goto = u"≡ " + goto
                try:
                    line = f.index(goto) + (2 if header else 0) + (1 if self.show_parent() else 0)
                    pt = self.view.text_point(line, 2)
                except ValueError:
                    pass

            self.view.sel().clear()
            self.view.sel().add(Region(pt, pt))
            self.view.show_at_center(Region(pt, 0))
        elif not f and not indent: # empty folder?
            pt = self.view.text_point(2, 0)
            self.view.sel().clear()
            self.view.sel().add(Region(pt, pt))
        else:
            self.view.sel().clear()
            self.view.sel().add(Region(name_point, name_point))
            self.view.show_at_center(name_point)

    def ls(self, path, names, goto='', indent=''):
        f = []
        tab = self.view.settings().get('tab_size')
        line = self.view.line(self.view.sel()[0].a)
        content = self.view.substr(line).replace('\t', ' '*tab)
        ind = re.compile('^(\s*)').match(content).group(1)
        level = indent * int((len(ind) / tab) + 1) if ind else indent
        # generating dirs list first
        for name in names:
            if isdir(join(path, goto, name)):
                name = ''.join([level, u"▸ ", name, os.sep])
                f.append(name)
        # generating files list
        for name in names:
            if not isdir(join(path, goto, name)):
                name = ''.join([level, u"≡ ", name])
                f.append(name)
        return f

    def is_hidden(self, filename):
        tests = self.view.settings().get('dired_hidden_files_patterns', ['.*'])
        if isinstance(tests, str):
            tests = [tests]
        if any(fnmatch.fnmatch(filename, pattern) for pattern in tests):
            return True
        if sublime.platform() != 'windows':
            return False
        # check for attribute on windows:
        try:
            attrs = ctypes.windll.kernel32.GetFileAttributesW(join(self.path, filename))
            assert attrs != -1
            result = bool(attrs & 2)
        except (AttributeError, AssertionError):
            result = False
        return result

    def vcs_check(self, edit, path, names, git='git'):
        if any(c for c in '~*?[]' if c in git):
            match = glob.glob(os.path.expanduser(git))
            if match:
                git = match[0]
            else:
                sublime.error_message('FileBrowser:\n'
                    'It seems like you use wildcards in "git_path": "%s".\n'
                    'But the pattern cannot be found, please, fix it '
                    'or use absolute path without wildcards.' % git)

        shell = True if sublime.platform()=='windows' else False
        try:
            p = subprocess.Popen([git, 'status', '-z'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=path, shell=shell)
            git_output = p.communicate()[0]
            p = subprocess.Popen([git, 'rev-parse', '--show-toplevel'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=path, shell=shell)
            root = p.communicate()[0].decode('utf-8').strip('\n')
        except:
            pass # cant catch it, perhaps Im missing something obvious :/
        else:
            if git_output:
                git_output = str(git_output, 'utf-8').split('\x00') if ST3 else git_output.split('\00')
                self.changed_items = dict((i[3:], i[1]) for i in git_output if i != '')
                sublime.set_timeout(lambda p=path, r=root: self.vcs_colorized(p, r), 1)

    def vcs_colorized(self, path, root):
        rgns, modified, untracked = [], [], []
        path = normpath(path)
        files_regions = dict((normpath(join(path, f)), r) for f, r in zip(self.get_all(), self.view.split_by_newlines(self.fileregion())))
        colorblind = self.view.settings().get('vcs_color_blind', False)
        for fn in self.changed_items.keys():
            full_fn = normpath(join(root, fn if ST3 else unicode(fn, 'utf-8')))
            r = files_regions.get(full_fn, 0)
            if r:
                content = self.view.substr(r)
                indent  = len(re.match(r'^(\s*)', content).group(1))
                icon = r.a + indent
                r = Region(icon, icon + (1 if not colorblind else 0))
                rgns.append((r, self.changed_items[fn]))
        for r, status in rgns:
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


# NAVIGATION #####################################################

class DiredNextLineCommand(TextCommand, DiredBaseCommand):
    def run(self, edit, forward=None):
        self.move(forward)


class DiredMoveCommand(TextCommand, DiredBaseCommand):
    def run(self, edit, **kwargs):
        if kwargs and kwargs["to"]:
            self.move_to_extreme(kwargs["to"])
            return
        elif kwargs and kwargs["duplicate"]:
            self.items = self._get_items(self.path)
            self.cursor = self.view.substr(self.view.line(self.view.sel()[0].a))[2:]
            self._duplicate(duplicate=kwargs["duplicate"])
        else:
            files = self.get_marked() or self.get_selected()
            if files:
                prompt.start('Move to:', self.view.window(), self.path, self._move)

    def _get_items(self, path):
        files = self.get_marked() or self.get_selected()
        path = normpath(normcase(path))
        for filename in files:
            fqn = normpath(normcase(join(self.path, filename)))
            yield fqn

    def _move(self, path):
        if not isabs(path):
            path = join(self.path, path)
        if not isdir(path):
            sublime.error_message(u'Not a valid directory: {0}'.format(path))
            return
        for fqn in self._get_items(path):
            if fqn != path:
                shutil.move(fqn, path)
        self.view.run_command('dired_refresh')

    def _duplicate(self, duplicate=''):
        fqn = next(self.items)
        for i in itertools.count(2):
            p, n = os.path.split(fqn)
            cfp = u"{1} {0}.{2}".format(i, join(p, n.split('.')[0]), '.'.join(n.split('.')[1:]))
            if os.path.isfile(cfp) or os.path.isdir(cfp):
                pass
            else:
                break
        if duplicate == 'rename':
            prompt.start('New name:', self.view.window(), os.path.basename(cfp), self._copy_duplicate, rename=(fqn, cfp, self.cursor))
        else:
            self._copy_duplicate(fqn, cfp, 0)

    def _copy_duplicate(self, fqn, cfp, int):
        if isdir(fqn):
            if not isdir(cfp):
                shutil.copytree(fqn, cfp)
            else:
                print(*("\nSkip! Folder with this name exists already:", cfp), sep='\n', end='\n\n')
        else:
            if not isfile(cfp):
                shutil.copy2(fqn, cfp)
            else:
                print(*("\nSkip! File with this name exists already:", cfp), sep='\n', end='\n\n')
        try:
            if int == 0:
                self._duplicate()
            elif int == 1:
                self._duplicate(duplicate='rename')
        except StopIteration:
            self.view.run_command('dired_refresh', {"goto": self.cursor})


class DiredSelect(TextCommand, DiredBaseCommand):
    def run(self, edit, new_view=0, other_group=0, preview=0, and_close=0, inline=0):
        path = self.path
        filenames = self.get_selected() if not new_view else self.get_marked() or self.get_selected()

        # If reuse view is turned on and the only item is a directory, refresh the existing view.
        if not new_view and reuse_view():
            fqn = join(path, filenames[0])
            if inline and '<empty>' == fqn[~6:]:
                return
            if len(filenames) == 1 and isdir(fqn):
                if inline:
                    # if directory was unfolded, then it’ll be folded and unfolded again
                    self.view.run_command('dired_fold', {'update': True})
                show(self.view.window(), fqn, view_id=self.view.id(), inline=inline)
                return
            elif len(filenames) == 1 and filenames[0] == PARENT_SYM:
                self.view.window().run_command("dired_up")
                return

        if other_group or preview or and_close:
            # we need group number of FB view, hence twice check for other_group
            dired_view = self.view
            nag = self.view.window().active_group()
        w = self.view.window()
        for filename in filenames:
            fqn = join(path, filename.replace('<empty>', '').rstrip())
            if exists(fqn): # ignore 'item <error>'
                if isdir(fqn):
                    show(w, fqn, ignore_existing=new_view)
                else:
                    if preview:
                        w.focus_group(self._other_group(w, nag))
                        v = w.open_file(fqn, sublime.TRANSIENT)
                        w.set_view_index(v, self._other_group(w, nag), 0)
                        w.focus_group(nag)
                        w.focus_view(dired_view)
                        break # preview is possible for a single file only
                    else:
                        v = w.open_file(fqn)
                        if other_group:
                            w.focus_view(dired_view)
                            w.set_view_index(v, self._other_group(w, nag), 0)
                            w.focus_view(v)
        if and_close:
            w.focus_view(dired_view)
            w.run_command("close")
            w.focus_view(v)

    def _other_group(self, w, nag):
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
    def run(self, edit, update=''):
        v    = self.view
        line = v.line(v.sel()[0].a)
        current_region = v.indented_region(line.b)
        next_region    = v.indented_region(line.b + 2)
        is_folder      = 'directory' in v.scope_name(line.a)
        folded_subfolder = update and (next_region.contains(line) or next_region.empty() or next_region.contains(current_region))
        folded_folder    = update and current_region.empty() and next_region.empty()
        file_item_in_root  = not is_folder and current_region.empty()

        if folded_subfolder or folded_folder or file_item_in_root:
            # folding is not supposed to happen, so we exit
            return
        elif update or (is_folder and not next_region.empty() and not next_region.contains(line)):
            indented_region = next_region
        elif not current_region.empty():
            indented_region = current_region
            line = v.line(indented_region.a - 2)
        else:
            # this is not supposed to happen, but it does sometimes
            return
        name_point  = v.extract_scope(line.b - 1).a
        icon_region = Region(name_point - 2, name_point - 1)

        dired_count = v.settings().get('dired_count', 0)
        v.settings().set('dired_count', int(dired_count) - len(v.lines(indented_region)))

        if indented_region.b == v.size(): # MUST avoid new line at eof
            indented_region = Region(indented_region.a - 1, indented_region.b)

        v.set_read_only(False)
        v.replace(edit, icon_region, u'▸')
        v.erase(edit, indented_region)
        v.set_read_only(True)

        v.sel().clear()
        v.sel().add(Region(name_point, name_point))


class DiredUpCommand(TextCommand, DiredBaseCommand):
    def run(self, edit):
        parent = dirname(self.path.rstrip(os.sep))
        if parent != os.sep:
            parent += os.sep
        if parent == self.path:
            return

        view_id = (self.view.id() if reuse_view() else None)
        show(self.view.window(), parent, view_id, goto=basename(self.path.rstrip(os.sep)))


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
        where = ', '.join(join(self.path, p) for p in self.get_marked()) or self.path or ''
        args = {"panel": "find_in_files", "where": where, "replace": "", "reverse": "false"}
        sublime.active_window().run_command("show_panel", args)


# MARKING ###########################################################

class DiredMarkExtensionCommand(TextCommand, DiredBaseCommand):
    def run(self, edit):
        filergn = self.fileregion()
        if filergn.empty():
            return
        ext = self.view.substr(self.view.line(self.view.sel()[0].a)).split('.')[-1]
        pv = self.view.window().show_input_panel('Extension:', ext, self.on_done, None, None)
        pv.run_command("select_all")

    def on_done(self, ext):
        ext = ext.strip()
        if not ext:
            return
        if not ext.startswith('.'):
            ext = '.' + ext
        def _markfunc(oldmark, filename):
            return filename.endswith(ext) and True or oldmark
        self._mark(mark=_markfunc, regions=self.fileregion())


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

        # If markall is set, mark/unmark all files.  Otherwise only those that are selected.
        if markall:
            regions = [ filergn ]
        else:
            regions = self.view.sel()

        def _toggle(oldmark, filename):
            return not oldmark
        if mark == 'toggle':
            # Special internal case.
            mark = _toggle

        self._mark(mark=mark, regions=regions)

        # If there is no selection, move the cursor forward so the user can keep pressing 'm'
        # to mark successive files.
        if not markall and len(self.view.sel()) == 1 and self.view.sel()[0].empty():
            self.move(forward)


# MANIPULATION ######################################################

class DiredCreateCommand(TextCommand, DiredBaseCommand):
    def run(self, edit, which=None):
        assert which in ('file', 'directory'), "which: " + which

        # Is there a better way to do this?  Why isn't there some kind of context?  I assume
        # the command instance is global and really shouldn't have instance information.
        callback = getattr(self, 'on_done_' + which, None)
        self.view.window().show_input_panel(which.capitalize() + ':', '', callback, None, None)

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
            open(fqn, 'wb')

        self.view.run_command('dired_refresh', {'goto': value})


class DiredDeleteCommand(TextCommand, DiredBaseCommand):
    def run(self, edit, trash=False):
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
                msg = u"Cannot send to trash.\nPermanently " + msg.replace('D', 'd', 1)
                trash = False
            elif trash and need_confirm:
                msg = msg.replace('Delete', 'Send to trash', 1)

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
                                          +'\n'.join(errors).replace('Couldn\'t perform operation.', ''))
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
                    except: # failed getpreferredencoding
                        e = 'Unknown error'
                errors.append(u'{0}:\t{1}'.format(e, filename))
        self.view.run_command('dired_refresh')
        if errors:
            sublime.error_message(u'Some files couldn’t be deleted: \n\n' + '\n'.join(errors))


class DiredRenameCommand(TextCommand, DiredBaseCommand):
    def run(self, edit):
        if self.filecount():
            # Store the original filenames so we can compare later.
            self.view.settings().set('rename', self.get_all())
            self.view.settings().set('dired_rename_mode', True)
            self.view.settings().set('color_scheme', 'Packages/FileBrowser/dired-rename-mode.hidden-tmTheme')
            self.view.set_read_only(False)

            self.set_ui_in_rename_mode(edit)

            self.view.set_status("__FileBrowser__", u" 𝌆 [enter: Apply changes] [escape: Discard changes] ")

            # Mark the original filename lines so we can make sure they are in the same
            # place.
            r = self.fileregion()
            self.view.add_regions('rename', [ r ], '', '', MARK_OPTIONS)


class DiredRenameCancelCommand(TextCommand, DiredBaseCommand):
    """
    Cancel rename mode.
    """
    def run(self, edit):
        self.view.settings().erase('rename')
        self.view.settings().set('color_scheme', 'Packages/FileBrowser/dired.hidden-tmTheme')
        self.view.settings().set('dired_rename_mode', False)
        goto_file_name = self.get_selected()[0]
        if goto_file_name.endswith(os.sep):
            goto_file_name = goto_file_name[0:-1]
        self.view.run_command('dired_refresh', {"goto": goto_file_name})


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

        for region in self.view.get_regions('rename'):
            for line in self.view.lines(region):
                after.append(self._remove_ui(self.get_parent(line, self.view.substr(line).strip())))

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

        diffs = [ (b, a) for (b, a) in zip(before, after) if b != a ]
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
                    os.rename(orig, join(self.path, a))
                existing.remove(b)
                existing.add(a)

        self.view.erase_regions('rename')
        self.view.settings().erase('rename')
        self.view.settings().set('dired_rename_mode', False)
        self.view.settings().set('color_scheme', 'Packages/FileBrowser/dired.hidden-tmTheme')
        goto_file_name = self.get_selected()[0]
        if goto_file_name.endswith(os.sep):
            goto_file_name = goto_file_name[0:-1]
        self.view.run_command('dired_refresh', {"goto": goto_file_name})


# HELP ##############################################################

class DiredHelpCommand(TextCommand):
    def run(self, edit):
        view = self.view.window().new_file()
        view.settings().add_on_change('color_scheme', lambda: set_proper_scheme(view))
        view.set_name("Browse: shortcuts")
        view.set_scratch(True)
        view.settings().set('color_scheme','Packages/FileBrowser/dired.hidden-tmTheme')
        view.settings().set('line_numbers',False)
        view.run_command('dired_show_help')
        sublime.active_window().focus_view(view)


class DiredShowHelpCommand(TextCommand):
    def run(self, edit):
        COMMANDS_HELP = sublime.load_resource('Packages/FileBrowser/shortcuts.md') if ST3 else ''
        if not COMMANDS_HELP:
            dest = dirname(__file__)
            shortcuts = join(dest if dest!='.' else join(sublime.packages_path(), 'FileBrowser'), "shortcuts.md")
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
            return
        path = self.path[:-1]
        data = self.view.window().project_data()
        data['folders'] = data.get('folders') or {}
        folders = [f for f in data['folders'] if f['path'] != path]
        if len(folders) == len(data['folders']):
            folders.insert(0, { 'path': path })
        data['folders'] = folders
        self.view.window().set_project_data(data)
        self.view.window().run_command('dired_refresh')


class DiredOnlyOneProjectFolder(TextCommand, DiredBaseCommand):
    def run(self, edit):
        if not ST3:
            return
        msg = u"Set '{0}' as only one project folder (will remove all other folders from project)?".format(self.path)
        if sublime.ok_cancel_dialog(msg):
            data = self.view.window().project_data()
            data['folders'] = [{ 'path': self.path[:-1] }]
            self.view.window().set_project_data(data)
            self.view.window().run_command('dired_refresh')


class DiredQuickLookCommand(TextCommand, DiredBaseCommand):
    """
    quick look current file in mac or open in default app on other OSs
    """
    def run(self, edit):
        files = self.get_marked() or self.get_selected()
        if u"⠤" in files:
            files.remove(u"⠤")
        if sublime.platform() == 'osx':
            cmd = ["qlmanage", "-p"]
            for filename in files:
                fqn = join(self.path, filename)
                cmd.append(fqn)
            subprocess.call(cmd)
        else:
            import webbrowser
            for filename in files:
                fqn = join(self.path, filename)
                webbrowser.open_new_tab(fqn)


class DiredOpenExternalCommand(TextCommand, DiredBaseCommand):
    """
    open dir/file in external file explorer
    """
    def run(self, edit):
        self.view.window().run_command("open_dir", {"dir": self.path})


class DiredOpenInNewWindowCommand(TextCommand, DiredBaseCommand):
    def run(self, edit, project_folder=False):
        if project_folder:
            files = project_folder
        else:
            files = self.get_marked() or self.get_selected()
        items = []

        if ST3: # sublime.executable_path() is not available in ST2
            executable_path = sublime.executable_path()
            if sublime.platform() == 'osx':
                app_path = executable_path[:executable_path.rfind(".app/")+5]
                executable_path = app_path+"Contents/SharedSupport/bin/subl"
            items.append(executable_path)
            items.append("-n")

            for filename in files:
                fqn = join(self.path, filename)
                items.append(fqn)

            subprocess.Popen(items, cwd=self.path)

        else: # ST2
            items.append("-n")
            for filename in files:
                fqn = join(self.path or u'', filename)
                items.append(fqn)

            if sublime.platform() == 'osx':
                try:
                   subprocess.Popen(['subl'] + items, cwd=self.path)
                except:
                    try:
                        subprocess.Popen(['sublime'] + items, cwd=self.path)
                    except:
                        app_path = subprocess.Popen(["osascript", "-e" "tell application \"System Events\" to POSIX path of (file of process \"Sublime Text 2\" as alias)"], stdout=subprocess.PIPE).communicate()[0].rstrip()
                        subl_path = "{0}/Contents/SharedSupport/bin/subl".format(app_path)
                        subprocess.Popen([subl_path] + items, cwd=self.path)
            elif sublime.platform() == 'windows':
                # 9200 means win8
                shell = True if sys.getwindowsversion()[2] < 9200 else False
                items = [i.encode(locale.getpreferredencoding(False)) if sys.getwindowsversion()[2] == 9200 else i for i in items]
                try:
                    subprocess.Popen(['subl'] + items, cwd=self.path, shell=shell)
                except:
                    try:
                        subprocess.Popen(['sublime'] + items, cwd=self.path, shell=shell)
                    except:
                        subprocess.Popen(['sublime_text.exe'] + items, cwd=self.path, shell=shell)
            else:
                try:
                    subprocess.Popen(['subl'] + items, cwd=self.path)
                except:
                    subprocess.Popen(['sublime'] + items, cwd=self.path)

        def run_on_new_window():
            sublime.active_window().run_command("dired", { "immediate": True, "project": True, "other_group": "left"})

        sublime.set_timeout(run_on_new_window , 200)
        if not ST3:
            sublime.set_timeout(lambda: sublime.active_window().run_command("toggle_side_bar") , 200)


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
            sublime.set_timeout(lambda: w.set_view_index(view, 1, 0), 1)

    def on_load(self, view):
        self.on_new(view)
