#!/usr/bin/python
# -*- coding: utf-8 -*-

import re, os, fnmatch
import sublime
from sublime import Region
from os.path import isdir, join

if sublime.platform() == 'windows':
    import ctypes

ST3 = int(sublime.version()) >= 3000

if ST3:
    MARK_OPTIONS = sublime.DRAW_NO_OUTLINE
else:
    MARK_OPTIONS = 0


RE_FILE = re.compile(r'^(\s*)([^\\//].*)$')


def first(seq, pred):
    # I can't comprehend how this isn't built-in.
    return next((item for item in seq if pred(item)), None)


def sort_nicely(names):
    """ Sort the given list in the way that humans expect.
    Source: http://www.codinghorror.com/blog/2007/12/sorting-for-humans-natural-sort-order.html
    """
    convert = lambda text: int(text) if text.isdigit() else text.lower()
    alphanum_key = lambda key: [convert(c) for c in re.split('([0-9]+)', key)]
    names.sort(key=alphanum_key)


class DiredBaseCommand:
    """
    Convenience functions for dired TextCommands
    """
    @property
    def path(self):
        return self.view.settings().get('dired_path')

    def _remove_ui(self, s):
        return s.replace(u"▸ ", "").replace(u"▾ ", "").replace(u"≡ ", "")

    def filecount(self):
        """
        Returns the number of files and directories in the view.
        """
        return self.view.settings().get('dired_count', 0)

    def move_to_extreme(self, extreme="bof"):
        """
        Moves the cursor to the beginning or end of file list.  Clears all sections.
        """
        files = self.fileregion(with_parent_link=True)
        self.view.sel().clear()
        if extreme == "bof":
            ext_region = Region(files.a, files.a)
        else:
            name_point = self.view.extract_scope(self.view.line(files.b).a + 2).a
            ext_region = Region(name_point, name_point)
        self.view.sel().add(ext_region)
        self.view.show_at_center(ext_region)

    def move(self, forward=None):
        """
        Moves the cursor one line forward or backwards.  Clears all sections.
        """
        assert forward in (True, False), 'forward must be set to True or False'

        files = self.fileregion(with_parent_link=True)
        if files.empty():
            return

        sels = list(self.view.sel())
        new_sels = []

        for s in sels:
            pt = s.a
            if files.contains(pt):
                # Try moving by one line.
                line = self.view.line(pt)
                pt = forward and (line.b + 1) or (line.a - 1)
            if not files.contains(pt):
                # Not (or no longer) in the list of files, so move to the closest edge.
                pt = (pt > files.b) and files.b or files.a

            line = self.view.line(pt)
            scope = self.view.scope_name(line.a)
            if 'indent' in scope:
                name_point = self.view.extract_scope(line.a).b
            else:
                name_point = line.a + (2 if not 'parent_dir' in scope else 0)
            new_sels.append(name_point)

        self.view.sel().clear()
        for n in new_sels:
            self.view.sel().add(Region(n, n))
        name_point = new_sels[~0] if forward else new_sels[0]
        surroundings = True if self.view.rowcol(name_point)[0] < 3 else False
        self.view.show(name_point, surroundings)

    def show_parent(self):
        return sublime.load_settings('dired.sublime-settings').get('dired_show_parent', False)

    def fileregion(self, with_parent_link=False):
        """
        Returns a region containing the lines containing filenames.
        If there are no filenames None is returned.
        """
        if with_parent_link:
            all_items = sorted(self.view.find_by_selector('dired.item'))
        else:
            all_items = sorted(self.view.find_by_selector('dired.item.directory') +
                               self.view.find_by_selector('dired.item.file'))
        if not all_items:
            return None
        return Region(all_items[0].a, all_items[~0].b)

    def get_parent(self, line, text):
        '''
        Returns relative path for text using os.sep, e.g. bla\\parent\\text\\
        '''
        indent = self.view.indented_region(line.b)
        if 'directory' in self.view.scope_name(line.a):
            # line may have inline error msg after os.sep
            text = text.split(os.sep)[0] + os.sep
        while not indent.empty():
            parent = self.view.line(indent.a - 2)
            text   = os.path.join(self.view.substr(parent).lstrip(), text.lstrip())
            indent = self.view.indented_region(parent.a)
        return text

    def get_all(self):
        """
        Returns a list of all filenames in the view.
        """
        return [self._remove_ui(RE_FILE.match(self.get_parent(l, self.view.substr(l))).group(2)) for l in self.view.lines(self.fileregion())]

    def get_selected(self, parent=True):
        """
        Returns a list of selected filenames.
        """
        names = set()
        fileregion = self.fileregion(with_parent_link=parent)
        if not fileregion:
            return None
        for sel in self.view.sel():
            lines = self.view.lines(sel)
            for line in lines:
                if fileregion.contains(line):
                    text = self.view.substr(line)
                    if text:
                        names.add(self._remove_ui(RE_FILE.match(self.get_parent(line, text)).group(2)))
        names = list(names)
        sort_nicely(names)
        return names

    def get_marked(self):
        lines = []
        if self.filecount():
            for region in self.view.get_regions('marked'):
                lines.extend(self.view.lines(region))
        return [self._remove_ui(RE_FILE.match(self.get_parent(line, self.view.substr(line))).group(2)) for line in lines]

    def _mark(self, mark=None, regions=None):
        """
        Marks the requested files.

        mark
            True, False, or a function with signature `func(oldmark, filename)`.  The function
            should return True or False.

        regions
            Either a single region or a sequence of regions.  Only files within the region will
            be modified.
        """

        # Allow the user to pass a single region or a collection (like view.sel()).
        if isinstance(regions, Region):
            regions = [regions]

        filergn = self.fileregion()

        # We can't update regions for a key, only replace, so we need to record the existing
        # marks.
        previous = [m for m in self.view.get_regions('marked') if not m.empty()]
        marked = {}
        for r in previous:
            item = self._remove_ui(RE_FILE.match(self.get_parent(r, self.view.substr(r))).group(2))
            marked[item] = r

        for region in regions:
            for line in self.view.lines(region):
                if filergn.contains(line):
                    indent, text = RE_FILE.match(self.view.substr(line)).groups()
                    filename = self._remove_ui(self.get_parent(line, text))

                    if mark not in (True, False):
                        newmark = mark(filename in marked, filename)
                        assert newmark in (True, False), u'Invalid mark: {0}'.format(newmark)
                    else:
                        newmark = mark

                    if newmark:
                        name_region = Region(line.a + len(indent) + 2, line.b)  # do not mark UI elements
                        marked[filename] = name_region
                    else:
                        marked.pop(filename, None)

        if marked:
            r = sorted(list(marked.values()), key=lambda region: region.a)
            self.view.add_regions('marked', r, 'dired.marked', '', MARK_OPTIONS)
        else:
            self.view.erase_regions('marked')

    def set_ui_in_rename_mode(self, edit):
        header = self.view.settings().get('dired_header', False)
        if header:
            regions = self.view.find_by_selector('text.dired header.dired punctuation.definition.separator.dired')
        else:
            regions = self.view.find_by_selector('text.dired dired.item.parent_dir')
        if not regions:
            return
        region = regions[0]
        start = region.begin()
        self.view.erase(edit, region)
        if header:
            new_text = u"——[RENAME MODE]——" + u"—"*(region.size()-17)
        else:
            new_text = u"⠤ [RENAME MODE]"
        self.view.insert(edit, start, new_text)

    def set_status(self):
        # if view isnot focused, view.window() may be None
        window          = self.view.window() or sublime.active_window()
        path_in_project = any(folder == self.path[:-1] for folder in window.folders())
        settings        = self.view.settings()
        show_hidden     = settings.get('dired_show_hidden_files', True)
        copied_items    = settings.get('dired_to_copy', [])
        cut_items       = settings.get('dired_to_move', [])
        status = u" 𝌆 [?: Help] {0}Hidden: {1}{2}{3}".format(
            'Project root, ' if path_in_project else '',
            'On' if show_hidden else 'Off',
            ', copied(%d)' % len(copied_items) if copied_items else '',
            ', cut(%d)' % len(cut_items) if cut_items else ''
        )
        self.view.set_status("__FileBrowser__", status)

    def ls(self, path, names, goto='', indent=''):
        items   = []
        tab     = self.view.settings().get('tab_size')
        line    = self.view.line(self.sel.a if self.sel is not None else self.view.sel()[0].a)
        content = self.view.substr(line).replace('\t', ' '*tab)
        ind     = re.compile('^(\s*)').match(content).group(1)
        level   = indent * int((len(ind) / tab) + 1) if ind else indent
        files   = []
        for name in names:
            if isdir(join(path, goto, name)):
                items.append(''.join([level, u"▸ ", name, os.sep]))
            else:
                files.append(''.join([level, u"≡ ", name]))
        items += files
        return items

    def is_hidden(self, filename, path, goto=''):
        if not (path or goto):  # special case for ThisPC
            return False
        tests = self.view.settings().get('dired_hidden_files_patterns', ['.*'])
        if isinstance(tests, str):
            tests = [tests]
        if any(fnmatch.fnmatch(filename, pattern) for pattern in tests):
            return True
        if sublime.platform() != 'windows':
            return False
        # check for attribute on windows:
        try:
            attrs = ctypes.windll.kernel32.GetFileAttributesW(join(path, goto, filename))
            assert attrs != -1
            result = bool(attrs & 2)
        except (AttributeError, AssertionError):
            result = False
        return result

    def prepare_filelist(self, names, path, goto, indent):
        show_hidden = self.view.settings().get('dired_show_hidden_files', True)
        if not show_hidden:
            names = [name for name in names if not self.is_hidden(name, path, goto)]
        sort_nicely(names)
        f = self.ls(path, names, goto=goto if indent else '', indent=indent)
        return f

    def prepare_treeview(self, names, path, goto, indent):
        f = self.prepare_filelist(names, path, goto, indent)
        line = self.view.line(self.sel if self.sel is not None else self.view.sel()[0])
        # line may have inline error msg after os.sep
        dir_name = self.view.substr(line).split(os.sep)[0].replace(u'▸', u'▾', 1) + os.sep
        if f:
            dired_count = self.view.settings().get('dired_count', 0)
            self.view.settings().set('dired_count', int(dired_count) + len(f))
            return '\n'.join([dir_name] + f)
        else:
            return '\t'.join([dir_name, '<empty>'])

    def restore_marks(self, marked=None):
        if marked:
            # Even if we have the same filenames, they may have moved so we have to manually
            # find them again.
            regions = []
            for line in self.view.lines(self.fileregion()):
                indent, text = RE_FILE.match(self.view.substr(line)).groups()
                filename = self._remove_ui(self.get_parent(line, text))
                if filename in marked:
                    name_region = Region(line.a + len(indent) + 2, line.b)  # do not mark UI elements
                    regions.append(name_region)
            self.view.add_regions('marked', regions, 'dired.marked', '', MARK_OPTIONS)
        else:
            self.view.erase_regions('marked')

    def restore_sels(self, sels=None):
        if sels:
            seled_fnames, seled_regions = sels
            regions = []
            for line in self.view.lines(self.fileregion()):
                indent, text = RE_FILE.match(self.view.substr(line)).groups()
                filename = self._remove_ui(self.get_parent(line, text))
                if filename in seled_fnames:
                    name_point = line.a + len(indent) + 2
                    regions.append(Region(name_point, name_point))
            if regions:
                return self._add_sels(regions)
            else:
                # e.g. when user remove file(s), we just restore sel RegionSet
                # despite positions may be wrong sometimes
                return self._add_sels(seled_regions)
        # fallback:
        return self._add_sels([Region(0, 0)])

    def _add_sels(self, sels):
        eof = self.view.size()
        self.view.sel().clear()
        for s in sels:
            if s.begin() <= eof:
                self.view.sel().add(s)
        if not self.view.sel():
            # all sels are more than eof
            s = Region(0, 0)
            self.view.sel().add(s)
        self.view.show_at_center(s)
