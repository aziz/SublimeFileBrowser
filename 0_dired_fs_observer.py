# coding: utf-8

'''This module creates a file system observer, which
    1. collect all open/expanded paths from all FileBrowser views and
    2. waiting for any changes in these paths (create/remove/modify file), and in case of such change
    3. schedule a refresh for corresponding view(s)

Filename of this module starts with 0_ because we want it being loaded before other FileBrowser
modules, so we can check if auto-refresh is functional.
The reason why we cannot check functionality here, but have to in the other module, is because
dired.py module is refreshing existing views on start-up, thus before checking presence of
auto-refresh, we must be sure that Refresh command is functional (i.e. dired.py is loaded).
In the other words, the algorithm is after we sure that
    1) all views are loaded (see dired.plugin_loaded),
    2) auto-refresh is presented,
then, finally,
    3) we add callback on change of dired_autorefresh setting (so user can disable it globally).
That is why this module must be loaded first, but its presence is checked in the other module.
'''

from __future__ import print_function
import sublime, os, datetime

try:  # unavailable dependencies shall not break basic functionality
    import package_events
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    Observer = None
    FileSystemEventHandler = object

ST3 = int(sublime.version()) >= 3000

if ST3:
    from functools import reduce
    from .common import emit_event
else:  # ST2 imports
    from common import emit_event


def plugin_loaded():
    global observer
    observer = ObservePaths()


def plugin_unloaded():
    global observer
    if 'observer' in globals():
        print('\nShutting down observer:', observer)
    else:
        return
    if observer is not None:
        observer.observer.stop()
        package_events.unlisten(u'FileBrowser', observer.dired_event_handler)
        package_events.unlisten(u'FileBrowserWFS', observer.event_handler.update_paths)
        observer.observer.join()
    del observer
    print('BOOM!!1 done...\n')


REFRESH_TIMEOUT  = 1000  # milliseconds: auto-refresh shall not happen more than once per REFRESH_TIMEOUT
SCHEDULE_REFRESH = 700   # milliseconds: time out for checking REFRESH_TIMEOUT


def time_out(past, now):
    return (now - past) > datetime.timedelta(milliseconds=REFRESH_TIMEOUT)


def refresh(views, erase_settings=False):
    '''
    views
        list of integers which are view.id(), can be empty
    erase_settings
        boolean, can be True after change of global setting dired_autorefresh
    '''
    if not views and not erase_settings:
        def is_dired(view): return view.settings() and view.settings().get("dired_path")
    else:
        def is_dired(view): return False

    for w in sublime.windows():
        for v in w.views():
            if v.id() in views or is_dired(v):
                if erase_settings:
                    v.settings().erase('dired_autorefresh')
                v.run_command('dired_refresh')


class ObservePaths(object):
    def __new__(cls):
        if Observer is None:
            return None
        return object.__new__(cls)

    def __init__(self):
        self.observer = Observer()
        self.event_handler = ReportEvent()
        self.paths = {}
        self.observer.start()
        package_events.listen(u'FileBrowser', self.dired_event_handler)

    def dired_event_handler(self, package, event, payload):
        '''receiving args from common.emmit_event'''
        def view_closed(view): self.paths.pop(view, None)

        def start_refresh(view, path):
            self.paths.update({view: [path.rstrip(os.sep)] if path else []})

        def finish_refresh(view, paths):
            if not paths:
                return

            old_paths = sorted(self.paths.get(view, []))
            paths = sorted(paths)
            if paths == old_paths:
                return

            self.paths.update({view: sorted(p for p in
                              set(old_paths + [p.rstrip(os.sep) for p in paths])
                              if os.path.exists(p))})
            self.observer.unschedule_all()
            for p in reduce(lambda i, j: i + j, self.paths.values()):
                self.observer.schedule(self.event_handler, p)

        def fold(view, path):
            p = set(self.paths.get(view, [])) - set([path.rstrip(os.sep)])
            finish_refresh(view, list(p))

        def toggle_watch_all(watch):
            '''watch is boolean or None, global setting dired_autorefresh'''
            views = self.paths.keys()
            if not watch:
                self.paths = {}
            sublime.set_timeout(lambda: refresh(views, erase_settings=(not watch)), 1)

        case = {
            'start_refresh': lambda: start_refresh(*payload),
            'finish_refresh': lambda: finish_refresh(*payload),
            'view_closed': lambda: view_closed(payload),
            'fold': lambda: fold(*payload),
            'stop_watch': lambda: view_closed(payload),
            'toggle_watch_all': lambda: toggle_watch_all(payload)
        }
        case[event]()
        emit_event(u'', self.paths, plugin=u'FileBrowserWFS')


class ReportEvent(FileSystemEventHandler):
    def __init__(self):
        self.paths = {}
        self.ignore_views = set()
        self.scheduled_views = {}
        package_events.listen(u'FileBrowserWFS', self.update_paths)

    def update_paths(self, package, event, payload):
        if event == u'ignore_view':
            self.ignore_views.update([payload])
            return
        elif event == u'watch_view':
            self.ignore_views -= set([payload])
            return
        self.paths = payload

    def on_any_event(self, event):
        '''
        File system event received from watchdog module,
        not to be confused with package_events which we use for internal communication
        dir(event) = ['event_type', 'is_directory', 'key', 'src_path']
        '''
        src_path = event.src_path
        path = src_path if event.is_directory else os.path.dirname(src_path)

        for v, p in self.paths.items():
            if any(i in p for i in (src_path, path)) and v not in self.ignore_views:
                if not self.scheduled_views:
                    self.schedule_refresh(v, datetime.datetime.now())
                else:
                    self.scheduled_views.update({v: datetime.datetime.now()})

    def schedule_refresh(self, view=None, at=None):
        now = datetime.datetime.now()
        if view and at:
            if time_out(at, now):
                sublime.set_timeout(self.schedule_refresh, SCHEDULE_REFRESH)
                return
            else:
                self.scheduled_views.update({view: at})

        if not self.scheduled_views:
            return

        views = [v for v, t in self.scheduled_views.items() if time_out(t, now)]
        for v in views:
            self.scheduled_views.pop(v, None)
        if views:
            sublime.set_timeout(lambda: refresh(views), 1)
        sublime.set_timeout(self.schedule_refresh, SCHEDULE_REFRESH)
        return


if not ST3:
    plugin_loaded()
    unload_handler = plugin_unloaded
