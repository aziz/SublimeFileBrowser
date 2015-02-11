import sublime, sublime_plugin, os
ST3 = int(sublime.version()) >= 3000

class SublimeFileBrowserFixUpPaths(sublime_plugin.TextCommand):
    '''
    usage: open console and run:
        view.run_command('sublime_file_browser_fix_up_paths')

    purpose: ensure that all paths end with os.sep
    '''
    def run(self, edit):
        for w in sublime.windows():
            for v in w.views():
                if v.settings():
                    p = v.settings().get("dired_path")
                    if p and p[~0] != os.sep:
                        v.settings().set("dired_path", p+os.sep)

        jp = sublime.load_settings('dired.sublime-settings').get('dired_jump_points', {})
        if jp:
            fix_jp = dict((n if ST3 else n.decode('utf8'), t if t[~0]==os.sep else t+os.sep) for n, t in jp.items())
            sublime.load_settings('dired.sublime-settings').set('dired_jump_points', fix_jp)
            sublime.save_settings('dired.sublime-settings')

        print('\nFileBrowser:\n\tAll fixed. Thank you for patience!\n')