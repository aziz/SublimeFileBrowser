# coding: utf8

'''This module contains all commands for operations with files:
    create, delete, rename, copy, and move
'''

from __future__ import print_function
import sublime
from sublime import Region
from sublime_plugin import TextCommand
import os, shutil, tempfile, itertools, threading
from os.path import basename, dirname, isdir, isfile, exists, join

ST3 = int(sublime.version()) >= 3000

if ST3:
    from .common import DiredBaseCommand, print, relative_path, NT, PARENT_SYM
    MARK_OPTIONS = sublime.DRAW_NO_OUTLINE
    try:
        import Default.send2trash as send2trash
    except ImportError:
        send2trash = None
else:  # ST2 imports
    import locale
    from common import DiredBaseCommand, print, relative_path, NT, PARENT_SYM
    MARK_OPTIONS = 0
    try:
        import send2trash
    except ImportError:
        send2trash = None


class DiredCreateCommand(TextCommand, DiredBaseCommand):
    def run(self, edit, which=None):
        assert which in ('file', 'directory'), "which: " + which
        self.index = self.get_all()
        rel_path   = relative_path(self.get_selected(parent=False) or '')

        self.which = which
        self.refresh = True
        pv = self.view.window().show_input_panel(which.capitalize() + ':', rel_path, self.on_done, None, None)
        pv.run_command('move_to', {'to': 'eol', 'extend': False})
        pv.settings().set('dired_create', True)
        pv.settings().set('which', which)
        pv.settings().set('dired_path', self.path)

    def on_done(self, value):
        value = value.strip()
        if not value:
            return False

        fqn = join(self.path, value)
        if exists(fqn):
            sublime.error_message(u'{0} already exists'.format(fqn))
            return False

        if self.which == 'directory':
            os.makedirs(fqn)
        else:
            with open(fqn, 'wb'):
                pass
        if self.refresh:  # user press enter
            self.view.run_command('dired_refresh', {'goto': fqn})

        # user press ctrl+enter, no refresh
        return fqn


class DiredCreateAndOpenCommand(DiredCreateCommand):
    '''Being called with ctrl+enter while user is in Create prompt
    So self.view is prompt view
    '''
    def run(self, edit):
        self.which = self.view.settings().get('which', '')
        if not self.which:
            return sublime.error_message('oops, does not work!')

        self.refresh = False
        value = self.view.substr(Region(0, self.view.size()))
        fqn = self.on_done(value)
        if not fqn:
            return sublime.status_message('oops, does not work!')

        sublime.active_window().run_command('hide_panel', {'cancel': True})

        dired_view = sublime.active_window().active_view()
        if dired_view.settings().has('dired_path'):
            self.refresh = True
        if self.which == 'directory':
            dired_view.settings().set('dired_path', fqn + os.sep)
        else:
            sublime.active_window().open_file(fqn)
        if self.refresh:
            dired_view.run_command('dired_refresh', {'goto': fqn})


class DiredDeleteCommand(TextCommand, DiredBaseCommand):
    def run(self, edit, trash=False):
        self.index = self.get_all()
        files = self.get_marked() or self.get_selected(parent=False)
        if not files:
            return sublime.status_message('Nothing chosen')

        msg, trash = self.setup_msg(files, trash)

        if trash:
            need_confirm = self.view.settings().get('dired_confirm_send2trash', True)
            msg = msg.replace('Delete', 'Delete to trash', 1)
            if not need_confirm or (need_confirm and sublime.ok_cancel_dialog(msg)):
                self._to_trash(files)
        elif not trash and sublime.ok_cancel_dialog(msg):
            self._delete(files)
        else:
            print("Cancel delete or something wrong in DiredDeleteCommand")

    def setup_msg(self, files, trash):
        '''If user send to trash, but send2trash is unavailable, we suggest deleting permanently'''
        # Yes, I know this is English.  Not sure how Sublime is translating.
        if len(files) == 1:
            msg = u"Delete {0}?".format(files[0])
        else:
            msg = u"Delete {0} items?".format(len(files))
        if trash and not send2trash:
            msg = u"Cannot delete to trash.\nPermanently " + msg.replace('D', 'd', 1)
            trash = False
        return (msg, trash)

    def _to_trash(self, files):
        '''Sending to trash might be slow
        So we start two threads which run _sender function in parallel and each of them waiting and
        setting certain event:
            1. remove one which signals that _sender need try to call send2trash for current file
               and if it fails collect error message (always ascii, no bother with encoding)
            2. report one which call _status function to display message on status-bar so user
               can see what is going on
        When loop in _sender is finished we refresh view and show errors if any.

        On Windows we call API directly in call_SHFileOperationW class.
        '''
        path = self.path
        if NT:  # use winapi directly, because better errors handling, plus GUI
            sources_move = [join(path, f) for f in files]
            return call_SHFileOperationW(self.view, sources_move, [], '$TRASH$')

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
        '''Delete is fast, no need to bother with threads or even status message
        But need to bother with encoding of error messages since they are vary,
        depending on OS and/or version of Python
        '''
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
        if not self.filecount():
            return sublime.status_message('Directory seems empty, nothing could be renamed')

        # Store the original filenames so we can compare later.
        path = self.path
        self.view.settings().set('rename', [f for f in self.get_all_relative('' if path == 'ThisPC\\' else path) if f and f != PARENT_SYM])
        self.view.settings().set('dired_rename_mode', True)
        self.view.set_read_only(False)

        self.set_ui_in_rename_mode(edit)

        self.view.set_status("__FileBrowser__", u" 𝌆 [enter: Apply changes] [escape: Discard changes] %s" % (u'¡¡¡DO NOT RENAME DISKS!!! you can rename their children though ' if path == 'ThisPC\\' else ''))

        # Mark the original filename lines so we can make sure they are in the same place.
        r = self.fileregion()
        self.view.add_regions('rename', [r], '', '', MARK_OPTIONS)


class DiredRenameCancelCommand(TextCommand, DiredBaseCommand):
    """Cancel rename mode"""
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
        after  = self.get_after()

        if len(after) != len(before):
            return sublime.error_message('You cannot add or remove lines')

        if len(set(after)) != len(after):
            return self.report_conflicts(before, after)

        self.apply_renames(before, after)

        self.view.erase_regions('rename')
        self.view.settings().erase('rename')
        self.view.settings().set('dired_rename_mode', False)
        self.view.run_command('dired_refresh', {'to_expand': self.re_expand_new_names()})

    def get_after(self):
        '''Return list of all filenames in the view'''
        self.index = self.get_all()
        path = self.path
        lines = self._get_lines(self.view.get_regions('rename'), self.fileregion())
        return [self._new_name(line, path=path) for line in lines]

    def _new_name(self, line, path=None, full=False):
        '''Return new name for line
        full
            if True return full path, otherwise relative to path variable
        path
            root, returning value is relative to it
        '''
        if full:
            parent = dirname(self.get_fullpath_for(line).rstrip(os.sep))
        else:
            parent = dirname(self.get_parent(line, path).rstrip(os.sep))
        new_name = self.view.substr(Region(self._get_name_point(line), line.b))
        if os.sep in new_name:  # ignore trailing errors, e.g. <empty>
            new_name = new_name.split(os.sep)[0] + os.sep
        return join(parent, new_name)

    def report_conflicts(self, before, after):
        '''
        before  list of all filenames before enter rename mode
        after   list of all filenames upon commit rename

        Warn about conflicts and print original (before) and conflicting (after) names for
        each item which cause conflict.
        '''
        sublime.error_message('There are duplicate filenames (see details in console)')
        self.view.window().run_command("show_panel", {"panel": "console"})
        print(*(u'\n   Original name: {0}\nConflicting name: {1}'.format(b, a)
                for (b, a) in zip(before, after) if b != a and a in before),
              sep='\n', end='\n\n')
        print('You can either resolve conflicts and apply changes or cancel renaming.\n')

    def apply_renames(self, before, after):
        '''args are the same as in self.report_conflicts
        If before and after differ, try to do actual rename for each pair
        Take into account directory symlinks on Unix-like OSes (they cannot be just renamed)
        In case of error, show message and exit skipping remain pairs
        '''
        # reverse order to allow renaming child and parent at the same time (tree view)
        diffs = list(reversed([(b, a) for (b, a) in zip(before, after) if b != a]))
        if not diffs:
            return sublime.status_message('Exit rename mode, no changes')

        path = self.path
        existing = set(before)
        while diffs:
            b, a = diffs.pop(0)

            if a in existing:
                # There is already a file with this name.  Give it a temporary name (in
                # case of cycles like "x->z and z->x") and put it back on the list.
                tmp = tempfile.NamedTemporaryFile(delete=False, dir=path).name
                os.unlink(tmp)
                diffs.append((tmp, a))
                a = tmp

            print(u'FileBrowser rename: {0} → {1}'.format(b, a))
            orig = join(path, b)
            if orig[~0] == '/' and os.path.islink(orig[:~0]):
                # last slash shall be omitted; file has no last slash,
                # thus it False and symlink to file shall be os.rename'd
                dest = os.readlink(orig[:~0])
                os.unlink(orig[:~0])
                os.symlink(dest, join(path, a)[:~0])
            else:
                try:
                    os.rename(orig, join(path, a))
                except OSError:
                    msg = (u'FileBrowser:\n\nError is occurred during renaming.\n'
                           u'Please, fix it and apply changes or cancel renaming.\n\n'
                           u'\t {0} → {1}\n\n'
                           u'Don’t rename\n'
                           u'  • non-existed file (cancel renaming to refresh)\n'
                           u'  • file if you’re not owner'
                           u'  • disk letter on Windows\n'.format(b, a))
                    sublime.error_message(msg)
                    return
            existing.remove(b)
            existing.add(a)

    def re_expand_new_names(self):
        '''Make sure that expanded directories will keep state if were renamed'''
        expanded = [self.view.line(r) for r in self.view.find_all(u'^\s*▾')]
        return [self._new_name(line, full=True) for line in expanded]


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
        self.show_hidden = self.view.settings().get('dired_show_hidden_files', True)
        self.set_status()


class DiredPasteFilesCommand(TextCommand, DiredBaseCommand):
    def run(self, edit):
        s = self.view.settings()
        sources_move = s.get('dired_to_move', [])
        sources_copy = s.get('dired_to_copy', [])
        if not (sources_move or sources_copy):
            return sublime.status_message('Nothing to paste')

        self.index  = self.get_all()
        path        = self.path if self.path != 'ThisPC\\' else ''
        rel_path    = relative_path(self.get_selected(parent=False) or '')
        destination = join(path, rel_path) or path
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


def _dups(sources_copy, destination):
    '''return list of files that should be duplicated silently'''
    return [p for p in sources_copy if os.path.split(p.rstrip(os.sep))[0] == destination.rstrip(os.sep)]


class call_SHFileOperationW(object):
    '''call Windows API for file operations'''
    def __init__(self, view, sources_move, sources_copy, destination):
        self.view = view
        if destination == '$TRASH$':
            self.shfow_d_thread = threading.Thread(target=self.caller, args=(3, sources_move, ''))
            self.shfow_d_thread.start()
            return
        if sources_move:
            self.shfow_m_thread = threading.Thread(target=self.caller, args=(1, sources_move, destination))
            self.shfow_m_thread.start()
        if sources_copy:
            # if user paste files in the same folder where they are then
            # it shall duplicate these files w/o asking anything
            dups = _dups(sources_copy, destination)
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
        '''mode is int: 1 (move), 2 (copy), 3 (delete)'''
        import ctypes
        if ST3: from Default.send2trash.plat_win import SHFILEOPSTRUCTW
        else:   from send2trash.plat_win import SHFILEOPSTRUCTW

        if duplicate:   fFlags = 8
        elif mode == 3: fFlags = 64  # send to recycle bin
        else:           fFlags = 0

        SHFileOperationW = ctypes.windll.shell32.SHFileOperationW
        SHFileOperationW.argtypes = [ctypes.POINTER(SHFILEOPSTRUCTW)]
        pFrom = u'\x00'.join(sources) + u'\x00'
        pTo   = (u'%s\x00' % destination) if destination else None
        args  = SHFILEOPSTRUCTW(wFunc  = ctypes.wintypes.UINT(mode),
                                pFrom  = ctypes.wintypes.LPCWSTR(pFrom),
                                pTo    = ctypes.wintypes.LPCWSTR(pTo),
                                fFlags = fFlags,
                                fAnyOperationsAborted = ctypes.wintypes.BOOL())
        out = SHFileOperationW(ctypes.byref(args))

        if not out and destination:  # 0 == success
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
            dups = _dups(sources_copy, destination)
            if dups:
                self.caller('dup', dups, destination)
                sources_copy = [p for p in sources_copy if p not in dups]
                if sources_copy:
                    self.caller('copy', sources_copy, destination)
            else:
                self.caller('copy', sources_copy, destination)

        self.check_errors()
        self.start_threads()

    def check_errors(self):
        msg = u'FileBrowser:\n\nSome files exist already, Cancel to skip all, OK to overwrite or rename.\n\n\t%s' % '\n\t'.join(self.errors.keys())
        self.actions = [['Overwrite', 'Folder cannot be overwritten'],
                        ['Duplicate', 'Item will be renamed automatically']]
        if self.errors and sublime.ok_cancel_dialog(msg):
            self.show_quick_panel()

    def start_threads(self):
        if self.threads:
            for t in self.threads:
                t.start()
            self.progress_bar(self.threads)

    def show_quick_panel(self):
        '''dialog asks if user would like to duplicate, overwrite, or skip item'''
        t, f    = self.errors.popitem()
        options = self.actions + [[u'from %s' % f, 'Skip'], [u'to   %s' % t, 'Skip']]
        done    = lambda i: self.user_input(i, f, t)
        sublime.set_timeout(lambda: self.window.show_quick_panel(options, done, sublime.MONOSPACE_FONT), 10)
        return

    def user_input(self, i, name, new_name):
        if i == 0:
            self._setup('overwrite', name, new_name)
        if i == 1:
            self.duplicate(name, new_name)
        if self.errors:
            self.show_quick_panel()
        else:
            self.start_threads()

    def caller(self, mode, sources, destination):
        for fqn in sources:
            new_name = join(destination, basename(fqn.rstrip(os.sep)))
            if mode == 'dup':
                self.duplicate(fqn, new_name)
            else:
                self._setup(mode, fqn, new_name)

    def duplicate(self, name, new_name):
        new_name = self.generic_nn(new_name)
        self._setup_copy(name, new_name, False)

    def _setup(self, mode, original, new_name):
        '''mode can be "move", "copy", "overwrite"'''
        if mode == 'move' and original != dirname(new_name):
            return self._setup_move(original, new_name)
        overwrite = mode == 'overwrite'
        if mode == 'copy' or overwrite:
            return self._setup_copy(original, new_name, overwrite)

    def _setup_move(self, original, new_name):
        if not exists(new_name):
            self._init_thread('move', original, new_name)
        else:
            self.errors.update({new_name: original})

    def _setup_copy(self, original, new_name, overwrite):
        '''overwrite is either True or False'''
        def __dir_or_file(mode, new_name, overwrite):
            exist = isdir(new_name) if mode == 'dir' else isfile(new_name)
            if not exist or overwrite:
                self._init_thread(mode, original, new_name)
            else:
                self.errors.update({new_name: original})
        if isdir(original):
            __dir_or_file('dir', new_name, overwrite)
        else:
            __dir_or_file('file', new_name, overwrite)

    def _init_thread(self, mode, source_name, new_name):
        '''mode can be "move", "dir", "file"'''
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
