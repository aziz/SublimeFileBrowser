#!/usr/bin/python
# -*- coding: utf-8 -*-

import re, os
import sublime
from sublime import Region

ST3 = int(sublime.version()) >= 3000

if ST3:
    MARK_OPTIONS = sublime.DRAW_NO_OUTLINE
else:
    MARK_OPTIONS = 0
    import locale


RE_FILE = re.compile(r'^([^\\//].*)$')

def first(seq, pred):
    # I can't comprehend how this isn't built-in.
    return next((item for item in seq if pred(item)), None)

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
            name_point = self.view.extract_scope(self.view.line(files.b).b - 1).a
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

        pt = self.view.sel()[0].a

        if files.contains(pt):
            # Try moving by one line.
            line = self.view.line(pt)
            pt = forward and (line.b + 1) or (line.a - 1)

        if not files.contains(pt):
            # Not (or no longer) in the list of files, so move to the closest edge.
            pt = (pt > files.b) and files.b or files.a

        line = self.view.line(pt)
        name_point = self.view.extract_scope(line.b - 1).a
        if any(s for s in ('extension', 'string.error') if s in self.view.scope_name(name_point)):
            name_point = self.view.extract_scope(name_point - 2).a
        if 'punctuation' in self.view.scope_name(name_point):
            name_point += 2 # fix for filenames w/o dot or whitespace
        self.view.sel().clear()
        self.view.sel().add(Region(name_point, name_point))
        surroundings = True if self.view.rowcol(name_point)[0] < 3 else False
        self.view.show(name_point, surroundings)

    def show_parent(self):
        return sublime.load_settings('dired.sublime-settings').get('dired_show_parent', False)

    def fileregion(self, with_parent_link=False):
        """
        Returns a region containing the lines containing filenames.  If there are no filenames
        Region(0,0) is returned.
        """
        if with_parent_link:
            all_items = sorted(self.view.find_by_selector('dired.item'))
        else:
            all_items = sorted(self.view.find_by_selector('dired.item.directory') +
                               self.view.find_by_selector('dired.item.file'))
        return Region(all_items[0].a, all_items[~0].b)

    def get_parent(self, line, text):
        '''
        Returns relative path for text using os.sep, e.g. bla\\parent\\text\\
        '''
        indent = self.view.indented_region(line.b)
        while not indent.empty():
            parent = self.view.line(indent.a - 2)
            text   = os.path.join(self.view.substr(parent).lstrip(), text.lstrip())
            indent = self.view.indented_region(parent.a)
        return text

    def get_all(self):
        """
        Returns a list of all filenames in the view.
        """
        return [ self._remove_ui(RE_FILE.match(self.get_parent(l, self.view.substr(l))).group(1)) for l in self.view.lines(self.fileregion()) ]


    def get_selected(self, parent=True):
        """
        Returns a list of selected filenames.
        """
        names = set()
        fileregion = self.fileregion(with_parent_link=parent)
        for sel in self.view.sel():
            lines = self.view.lines(sel)
            for line in lines:
                if fileregion.contains(line):
                    text = self.view.substr(line)
                    if text:
                        names.add(self._remove_ui(RE_FILE.match(self.get_parent(line, text)).group(1)))
        return sorted(list(names))

    def get_marked(self):
        lines = []
        if self.filecount():
            for region in self.view.get_regions('marked'):
                lines.extend(self.view.lines(region))
        return [ self._remove_ui(RE_FILE.match(self.get_parent(line, self.view.substr(line))).group(1)) for line in lines ]


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
            regions = [ regions ]

        filergn = self.fileregion()

        # We can't update regions for a key, only replace, so we need to record the existing
        # marks.
        previous = self.view.get_regions('marked')
        marked = {}
        for r in previous:
            item = self._remove_ui(RE_FILE.match(self.view.substr(r)).group(1))
            marked[item] = r

        for region in regions:
            for line in self.view.lines(region):
                if filergn.contains(line):
                    text = self.view.substr(line)
                    filename = self._remove_ui(RE_FILE.match(text).group(1))

                    if mark not in (True, False):
                        newmark = mark(filename in marked, filename)
                        assert newmark in (True, False), u'Invalid mark: {0}'.format(newmark)
                    else:
                        newmark = mark

                    if newmark:
                        name_region = Region(line.a + 2, line.b) # do not mark UI elements
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
