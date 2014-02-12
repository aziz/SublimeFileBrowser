#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import print_function
import sublime
from sublime import Region
from sublime_plugin import WindowCommand, TextCommand
import os, re, shutil, tempfile, subprocess, itertools
from os.path import basename, dirname, isdir, isfile, exists, join, isabs, normpath, normcase

ST3 = int(sublime.version()) >= 3000
ECODING = 'UTF-8'

if ST3:
    from .common import RE_FILE, DiredBaseCommand
    from . import prompt
    from .show import show
    from .jumping import jump_names
    MARK_OPTIONS = sublime.DRAW_NO_OUTLINE
    PARENT_SYM = "⠤"
    try:
        import Default.send2trash as send2trash
    except ImportError:
        send2trash = None
else:
    import locale
    from common import RE_FILE, DiredBaseCommand
    import prompt
    from show import show
    from jumping import jump_names
    MARK_OPTIONS = 0
    PARENT_SYM = "⠤".decode(ECODING)
    try:
        import send2trash
    except ImportError:
        send2trash = None


# Each dired view stores its path in its local settings as 'dired_path'.

COMMANDS_HELP = """\

Browse Shortcu
+-------------------------------+------------------------+
| Command                       | Shortcut               |
|-------------------------------+------------------------|
| Help page                     | ?                      |
| Toggle mark                   | m                      |
| Toggle mark and move down     | shift+down             |
| Toggle mark and move up       | shift+up               |
| Toggle all marks              | t                      |
| Unmark all                    | u                      |
| Mark by extension             | *                      |
| Rename                        | R                      |
| Move                          | M                      |
| Delete                        | D                      |
| Send to trash                 | S                      |
| Create directory              | cd                     |
| Create file                   | cf                     |
| Open file/view directory      | enter/o                |
| Open in Finder/Explorer       | \                      |
| Open in new window            | w                      |
| Go to parent directory        | backspace              |
| Go to directory               | g                      |
| Quck jump to directory        | p                      |
| Create/Edit/Remove jump point | P                      |
| Go to first                   | super+up / ctrl+home   |
| Go to last                    | super+down / ctrl+end  |
| Move to previous              | k/up                   |
| Move to next                  | j/down                 |
| Jump to                       | /                      |
| Refresh view                  | r                      |
| Toggle hidden files           | h                      |
| Quicklook for Mac             | space                  |
+-------------------------------+------------------------+

In Rename Mode:
+--------------------------+-------------+
| Command                  | Shortcut    |
|--------------------------|-------------|
| Apply changes            | enter       |
| Discard changes          | escape      |
+--------------------------+-------------+
"""

def reuse_view():
    return sublime.load_settings('dired.sublime-settings').get('dired_reuse_view', False)

def sort_nicely(l):
    """ Sort the given list in the way that humans expect.
    Source: http://www.codinghorror.com/blog/2007/12/sorting-for-humans-natural-sort-order.html
    """
    convert = lambda text: int(text) if text.isdigit() else text.lower()
    alphanum_key = lambda key: [convert(c) for c in re.split('([0-9]+)', key)]
    l.sort(key=alphanum_key)

def has_hidden_attribute(filepath):
    if sublime.platform() == 'windows':
        import ctypes
        try:
            attrs = ctypes.windll.kernel32.GetFileAttributesW(filepath)
            assert attrs != -1
            result = bool(attrs & 2)
        except (AttributeError, AssertionError):
            result = False
        return result
    elif sublime.platform() == 'linux':
        return False


class DiredCommand(WindowCommand):
    """
    Prompt for a directory to display and display it.
    """
    def run(self, immediate=False):
        if immediate:
            show(self.window, self._determine_path())
        else:
            prompt.start('Directory:', self.window, self._determine_path(), self._show)

    def _show(self, path):
        show(self.window, path)

    def _determine_path(self):
        # Use the current view's directory if it has one.
        view = self.window.active_view()
        path = view and view.file_name()
        if path:
            return dirname(path)

        # Use the first project folder if there is one.
        data = self.window.project_data() if ST3 else None
        if data and 'folders' in data:
            folders = data['folders']
            if folders:
                return folders[0]['path']

        # Use window folder if possible
        folders = self.window.folders()
        if len(folders) > 0:
            return folders[0]

        # Use the user's home directory.
        return os.path.expanduser('~')


class DiredRefreshCommand(TextCommand, DiredBaseCommand):
    """
    Populates or repopulates a dired view.
    """
    def run(self, edit, goto=None):
        """
        goto
            Optional filename to put the cursor on.
        """
        print(self.view.settings())

        status = " 𝌆 [?: Help] " if ST3 else " [?: Help] "
        show_hidden = self.view.settings().get('dired_show_hidden_files', True)
        status += 'Hidden: ON' if show_hidden else 'Hidden: OFF'
        self.view.set_status("__FileBrowser__", status)

        path = self.path
        try:
            names = os.listdir(path)
            if not show_hidden:
                names = [name for name in names if not (name.startswith('.') or  has_hidden_attribute(join(path, name)))]
            sort_nicely(names)
        except WindowsError as e:
            self.view.run_command("dired_up")
            self.view.set_read_only(False)
            self.view.insert(edit, self.view.line(self.view.sel()[0]).b,
                             '\t<%s>' % str(e).split(':')[0]
                             .replace('[Error 5] ', 'Access denied'))
            self.view.set_read_only(True)
        else:
            self.continue_refreshing(edit, path, names, goto)

    def continue_refreshing(self, edit, path, names, goto=None):
        f = []

        # generating dirs list first
        for name in names:
            if isdir(join(path, name)):
                try:
                    name = "▸ ".decode(ECODING) + name + os.sep
                except:
                    name = "▸ " + name + os.sep
                f.append(name)

        # generating files list
        for name in names:
            if not isdir(join(path, name)):
                try:
                    name = "≡ ".decode(ECODING) + name
                except:
                    name = "≡ " + name
                f.append(name)

        marked = set(self.get_marked())

        name = jump_names().get(path)
        if name:
            caption = "{0} -> {1}".format(name, path)
        else:
            caption = path
        text = [ caption ]
        try:
            text.append(len(caption)*('—'.decode(ECODING)))
        except:
            text.append(len(caption)*('—'))
        if not f or self.show_parent():
            text.append(PARENT_SYM)
        text.extend(f)

        self.view.set_read_only(False)

        self.view.erase(edit, Region(0, self.view.size()))
        self.view.insert(edit, 0, '\n'.join(text))
        self.view.set_syntax_file('Packages/FileBrowser/dired.hidden-tmLanguage')
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
        if f:
            pt = self.fileregion(with_parent_link=True).a
            if goto:
                if isdir(join(path, goto)) and not goto.endswith(os.sep):
                    try:
                        goto = "▸ ".decode(ECODING) + goto + os.sep
                    except:
                        goto = "▸ " + goto + os.sep
                else:
                    try:
                        goto = "≡ ".decode(ECODING) + goto
                    except:
                        goto = "≡ " + goto
                try:
                    line = f.index(goto) + (3 if self.show_parent() else 2)
                    pt = self.view.text_point(line, 2)
                except ValueError:
                    pass

            self.view.sel().clear()
            self.view.sel().add(Region(pt, pt))
            self.view.show_at_center(Region(pt, pt))
        else: # empty folder?
            pt = self.view.text_point(2, 0)
            self.view.sel().clear()
            self.view.sel().add(Region(pt, pt))


class DiredNextLineCommand(TextCommand, DiredBaseCommand):
    def run(self, edit, forward=None):
        self.move(forward)


class DiredSelect(TextCommand, DiredBaseCommand):
    def run(self, edit, new_view=False):
        path = self.path
        filenames = self.get_selected()

        # If reuse view is turned on and the only item is a directory, refresh the existing view.
        if not new_view and reuse_view():
            if len(filenames) == 1 and isdir(join(path, filenames[0])):
                fqn = join(path, filenames[0])
                show(self.view.window(), fqn, view_id=self.view.id())
                return
            elif len(filenames) == 1 and filenames[0] == PARENT_SYM:
                self.view.window().run_command("dired_up")
                return

        for filename in filenames:
            fqn = join(path, filename)
            if '<' not in fqn: # ignore 'item <error>'
                if isdir(fqn):
                    show(self.view.window(), fqn, ignore_existing=new_view)
                else:
                    self.view.window().open_file(fqn)


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
            sublime.error_message('{0} already exists'.format(fqn))
            return

        if which == 'directory':
            os.makedirs(fqn)
        else:
            open(fqn, 'wb')

        self.view.run_command('dired_refresh', {'goto': value})


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


class DiredDeleteCommand(TextCommand, DiredBaseCommand):
    def run(self, edit, trash=False):
        files = self.get_marked() or self.get_selected()
        if files:
            # Yes, I know this is English.  Not sure how Sublime is translating.
            if len(files) == 1:
                msg = "Delete {0}?".format(files[0])
            else:
                msg = "Delete {0} items?".format(len(files))
            if trash:
                need_confirm = self.view.settings().get('dired_confirm_send2trash')
            if trash and not send2trash:
                msg = "Cannot send to trash.\nPermanently " + msg[0].lower() + msg[1:]
                trash = False
            elif trash and need_confirm:
                msg = msg.replace('Delete', 'Send to trash')

            if trash and send2trash:
                if not need_confirm or (need_confirm and sublime.ok_cancel_dialog(msg)):
                    self._to_trash(files)
            elif not trash and sublime.ok_cancel_dialog(msg):
                self._delete(files)
            else:
                print("Something wrong in DiredDeleteCommand")

    def _to_trash(self, files):
        import threading
        path = self.path
        def _status(filename='', done=False):
            if done:
                sublime.set_timeout(lambda: self.view.run_command('dired_refresh'), 1)
            else:
                status = u'Please, wait… Removing ' + filename
                sublime.set_timeout(lambda: self.view.set_status("__FileBrowser__", status), 1)
        def _sender(files, event_for_wait, event_for_set):
            for filename in files:
                event_for_wait.wait()
                event_for_wait.clear()
                if event_for_wait is remove_event:
                    send2trash.send2trash(join(path, filename))
                else:
                    _status(filename)
                event_for_set.set()
            _status(done=True)
        remove_event = threading.Event()
        report_event = threading.Event()
        t1 = threading.Thread(target=_sender, args=(files, remove_event, report_event))
        t2 = threading.Thread(target=_sender, args=(files, report_event, remove_event))
        t1.start()
        t2.start()
        report_event.set()

    def _delete(self, files):
        for filename in files:
            fqn = join(self.path, filename)
            if isdir(fqn):
                shutil.rmtree(fqn)
            else:
                os.remove(fqn)
        self.view.run_command('dired_refresh')


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
            sublime.error_message('Not a valid directory: {0}'.format(path))
            return
        for fqn in self._get_items(path):
            if fqn != path:
                shutil.move(fqn, path)
        self.view.run_command('dired_refresh')

    def _duplicate(self, duplicate=''):
        fqn = next(self.items)
        for i in itertools.count(2):
            p, n = os.path.split(fqn)
            cfp = "{1} {0}.{2}".format(i, join(p, n.split('.')[0]), '.'.join(n.split('.')[1:]))
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
                print(*("", "Skip! Folder with this name exists already:", cfp), sep='\n', end='\n\n')
        else:
            if not isfile(cfp):
                shutil.copy2(fqn, cfp)
            else:
                print(*("", "Skip! File with this name exists already:", cfp), sep='\n', end='\n\n')
        try:
            if int == 0:
                self._duplicate()
            elif int == 1:
                self._duplicate(duplicate='rename')
        except StopIteration:
            self.view.run_command('dired_refresh', {"goto": self.cursor})


class DiredRenameCommand(TextCommand, DiredBaseCommand):
    def run(self, edit):
        if self.filecount():
            # Store the original filenames so we can compare later.
            self.view.settings().set('rename', self.get_all())
            self.view.settings().set('dired_rename_mode', True)
            self.view.set_read_only(False)

            self.set_ui_in_rename_mode(edit)

            if ST3:
                self.view.set_status("__FileBrowser__", " 𝌆 [enter: Apply changes] [escape: Discard changes] ")
            else:
                self.view.set_status("__FileBrowser__", " [enter: Apply changes] [escape: Discard changes] ")

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
                after.append(self._remove_ui(self.view.substr(line).strip()))

        if len(after) != len(before):
            sublime.error_message('You cannot add or remove lines')
            return

        if len(set(after)) != len(after):
            sublime.error_message('There are duplicate filenames')
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

                print('dired rename: {0} --> {1}'.format(b, a))
                os.rename(join(self.path, b), join(self.path, a))
                existing.remove(b)
                existing.add(a)

        self.view.erase_regions('rename')
        self.view.settings().erase('rename')
        self.view.settings().set('dired_rename_mode', False)
        goto_file_name = self.get_selected()[0]
        if goto_file_name.endswith(os.sep):
            goto_file_name = goto_file_name[0:-1]
        self.view.run_command('dired_refresh', {"goto": goto_file_name})


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


class DiredQuickLookCommand(TextCommand, DiredBaseCommand):
    """
    quick look current file in mac in mac
    """
    def run(self, edit):
        files = self.get_marked() or self.get_selected()
        if "⠤" in files:
            files.remove("⠤")
        cmd = ["qlmanage", "-p"]
        for filename in files:
            fqn = join(self.path, filename)
            cmd.append(fqn)
        subprocess.call(cmd)


class DiredOpenExternalCommand(TextCommand, DiredBaseCommand):
    """
    open dir/file in external file explorer
    """
    def run(self, edit):
        self.view.window().run_command("open_dir", {"dir": self.path})


class DiredOpenInNewWindowCommand(TextCommand, DiredBaseCommand):
    def run(self, edit):
        items = []
        files = self.get_marked() or self.get_selected()

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
                fqn = join(self.path, filename)
                items.append(fqn)

            if sublime.platform() == 'osx':
               try:
                   subprocess.Popen(['subl'] + items, cwd=self.path)
               except:
                   try:
                       subprocess.Popen(['sublime'] + items, cwd=self.path)
                   except:
                       subprocess.Popen(['/Applications/Sublime Text 2.app/Contents/SharedSupport/bin/subl'] + items, cwd=self.path)
            elif sublime.platform() == 'windows':
               try:
                   subprocess.Popen(['subl'] + items, cwd=self.path, shell=True)
               except:
                   try:
                       subprocess.Popen(['sublime'] + items, cwd=self.path, shell=True)
                   except:
                       subprocess.Popen(['sublime_text.exe'] + items, cwd=self.path, shell=True)
            else:
               try:
                   subprocess.Popen(['subl'] + items, cwd=self.path)
               except:
                   subprocess.Popen(['sublime'] + items, cwd=self.path)



class DiredHelpCommand(TextCommand):
    def run(self, edit):
        view = self.view.window().new_file()
        view.set_name("Browse: shortcuts")
        view.set_scratch(True)
        view.settings().set('color_scheme','Packages/FileBrowser/dired.hidden-tmTheme')
        view.settings().set('line_numbers',False)
        view.run_command('dired_show_help')
        sublime.active_window().focus_view(view)


class DiredShowHelpCommand(TextCommand):
    def run(self, edit):
        self.view.erase(edit, Region(0, self.view.size()))
        self.view.insert(edit, 0, COMMANDS_HELP)
        self.view.sel().clear()
        self.view.set_read_only(True)


class DiredToggleHiddenFilesCommand(TextCommand):
    def run(self, edit):
        show = self.view.settings().get('dired_show_hidden_files', True)
        self.view.settings().set('dired_show_hidden_files', not show)
        self.view.run_command('dired_refresh')
