
# FileBrowser for SublimeText

Ditch sidebar and browse your files in a normal tab with keyboard, like a pro!

![SublimeFileBrowser Screenshot](http://cl.ly/image/2y1R143k3J1n/Screen%20Shot%202015-01-28%20at%208.22.56%20pm.png)

You can also use it as a sidebar that you can put on right or left side

![SublimeFileBrowser Screenshot2](http://cl.ly/image/2Y37412n351x/Screen%20Shot%202015-01-28%20at%208.33.28%20pm.png)

## Installation

You can install via [Sublime Package Control](http://wbond.net/sublime_packages/package_control)
Or you can clone this repo into your SublimeText Packages directory and rename it to `FileBrowser`

## Commands and Keybindings

This plugin does not add any keybindings for opening a new tab in *Browse Mode*. Although, the
commands to do that are available in *Command Palette* but it is recommended to bind <kbd>F1</kbd>
to open the current file directory in *Browse Mode* with this piece of code (that you can add to
your `Key Bindings - User` file):

``` json
{
  "keys": ["f1"],
  "command": "dired",
  "args": { "immediate": true }
}
```

You also can use optional arguments to tweak behavior:

* `"single_pane": true` — always use a single File Browser view, i.e. prefer to reuse existing one
  rather than create a new.
* `"other_group": "left"` (or `"right`) — open FileBrowser in other group, i.e. like sidebar; if
  you use `"left"` then all other tabs from left group will be moved into the right one.
* `"project": true` — always prefer project's directory(s) rather than path of current view.

You can mix these arguments as you like (perhaps, even bind several shortcuts for different cases);
e.g. to completely mimic sidebar, it would be:

``` json
{
  "keys": ["f1"],
  "command": "dired",
  "args": {
    "immediate": true,
    "single_pane": true,
    "other_group": "left",
    "project": true
  }
}
```

### Commands

| Commands                                 | Description                                                    |
| :--------------------------------------- | :------------------------------------------------------------- |
| **Browse Mode...**                       | Asks for a directory to open in browse mode                    |
| **Browse Mode: Current file or project** | Opens the directory of current file or project in browse mode  |
| **Browse Mode: Left Sidebar**            | Opens in browse mode as a sidebar on the left                  |
| **Browse Mode: Right Sidebar**           | Opens in browse mode as a sidebar on the right                 |
| **Browse Mode: Jump List**               | Shows the jump list view (see jump list section below)         |
| **Browse Mode: Jump List Quick Panel**   | Shows the jump list in quick panel                             |

### Shortcuts
##### General Shortcuts
| Command          | Shortcut     |
| :--------------- | :----------- |
| Shortcuts page   | <kbd>?</kbd> |
| Refresh view     | <kbd>r</kbd> |

##### Navigation Shortcuts
| Command                                               | Shortcut                                   |
| :---------------------------------------------------- | :----------------------------------------- |
| Move to previous                                      | <kbd>k</kbd> or <kbd>↑</kbd>               |
| Move to next                                          | <kbd>j</kbd> or <kbd>↓</kbd>               |
| Expand directory                                      | <kbd>l</kbd> or <kbd>→</kbd>               |
| Collapse directory                                    | <kbd>h</kbd> or <kbd>←</kbd>               |
| Toggle expand/collapse                                | <kbd>o</kbd>                               |
| Go to parent directory                                | <kbd>backspace</kbd>                       |
| Go to first                                           | <kbd>⌘+↑</kbd> or <kbd>ctrl+home</kbd>     |
| Go to last                                            | <kbd>⌘+↓</kbd> or <kbd>ctrl+end</kbd>      |
| Jump to                                               | <kbd>/</kbd>                               |
| Go to directory                                       | <kbd>g</kbd>                               |
| Quick jump to directory                               | <kbd>p</kbd>                               |
| Find in files                                         | <kbd>s</kbd>                               |
| Toggle mark                                           | <kbd>m</kbd>                               |
| Toggle mark and move down                             | <kbd>shift+↓</kbd>                         |
| Toggle mark and move up                               | <kbd>shift+↑</kbd>                         |
| Toggle all marks                                      | <kbd>t</kbd>                               |
| Unmark all                                            | <kbd>u</kbd>                               |
| Mark by extension                                     | <kbd>\*</kbd>                              |

##### Action Shortcuts
| Command                                               | Shortcut                                   |
| :---------------------------------------------------- | :----------------------------------------- |
| Rename                                                | <kbd>R</kbd>                               |
| Delete to trash                                       | <kbd>D</kbd>                               |
| Delete (does not send to trash)                       | <kbd>alt+shift+d</kbd>                     |
| Create directory                                      | <kbd>cd</kbd>, <kbd>enter</kbd>            |
| Create directory and open it                          | <kbd>cd</kbd>, <kbd>⌘+enter</kbd>          |
| Create file                                           | <kbd>cf</kbd>, <kbd>enter</kbd>            |
| Create file and open it                               | <kbd>cf</kbd>, <kbd>⌘+enter</kbd>          |
| Create/Edit/Remove jump point                         | <kbd>P</kbd>                               |
| Toggle hidden files                                   | <kbd>H</kbd>                               |
| Open in Finder/File Explorer                          | <kbd>\\</kbd>                              |
| Open in new window                                    | <kbd>W</kbd>                               |
| Open file in another group                            | <kbd>enter</kbd>                           |
| Open all marked items in new tabs                     | <kbd>⌘+enter</kbd> / <kbd>ctrl+enter</kbd> |
| Preview file in another group                         | <kbd>shift+enter</kbd>                     |
| Toggle add directory to project                       | <kbd>f</kbd>                               |
| Set current directory as the only one for the project | <kbd>F</kbd>                               |
| Quicklook for Mac or open in default app on other OSs | <kbd>space</kbd>                           |

##### *Rename Mode* Shortcuts
| Command          | Shortcut           |
| :--------------- | :----------------- |
| Apply changes    | <kbd>enter</kbd>   |
| Discard changes  | <kbd>escape</kbd>  |

**NOTE**: All these keyboard shortcuts can be customized in your own key-binding file. Open the
          default key-bindings file (`Preferences` → `Package Settings` → `FileBrowser` →
          `Keybinding — Default`) and copy the ones you want to change to your `Keybinding — User`
          file.

## Usage

### Selecting Files and Directories
You can select files and/or directories by marking them with <kbd>m</kbd>, or <kbd>Shift + ↑/↓</kbd>
or just use SublimeText multiple cursor feature and extend your cursor to the line that has those
files/directories.

You can expand or collapse a directory (or multiple directories using marking or multiple cursors)
by pressing <kbd>o</kbd>. <kbd>l</kbd> or <kbd>→</kbd> will also expand directories inline and
<kbd>h</kbd> or <kbd>←</kbd> will collapse.

### Search
Besides incremental search available by <kbd>/</kbd>, you also may use build-in "Goto Symbol…"
(<kbd>⌘+r</kbd> or <kbd>ctrl + r</kbd>) for fuzzy search.

### "Find in Files…" integration
Press <kbd>s</kbd> to summon "Find in Files…" panel — if you've marked some files they will fill
*Where* field, otherwise it will be filled by current directory path.

### Rename Mode
The rename command puts the view into **rename mode**. The view is made editable so files can be
renamed directly in the view using all of your SublimeText tools: multiple cursors, search and
replace, etc.

After you are done with editing press <kbd>enter</kbd> to commit your changes or <kbd>escape</kbd>
to cancel them.

### Cut, copy and paste files
You can move and copy files/folders. Shortcuts are quite standard: <kbd>x</kbd>, <kbd>c</kbd>, 
<kbd>v</kbd> with <kbd>⌘</kbd> or <kbd>ctrl</kbd>.

You can copy and/or cut as many items and from many locations as you like — status-bar will show 
amounts of copied and cut items.  
If you change your mind — <kbd>⌘+z</kbd> or <kbd>ctrl+z</kbd> will clear both lists. _Note_, those
lists are stored in FileBrowser settings file, so you can edit it by hand if need.

As soon as you paste, each item will be either copied or moved into folder under cursor.  
If you want to alter the destination path without moving cursor, you may do so with 
<kbd>⌘+shift+v</kbd> or <kbd>ctrl+shift+v</kbd> to open prompt; you may use prompt without copy/cut 
before, i.e. if those lists in settings file are empty then prompt will take marked or selected 
item(s) and suggest copying them.

On Windows all operations will be done via system API with all its features (renaming semantics, 
interactive overwrite, progress-bar, pause/cancel, and so on).

On other OSes all operations will be done via Python API, which is not that cool, but you will see 
a vague progress in status-bar and can choose what to do in case of conflicts (overwrite, duplicate, 
skip), however, there are some restrictions, e.g. folders cannot be overwritten or merged.

### Open in new window
Selecting a couple of files and/or directories (either by marking them or using the normal multiple
cursor feature of SublimeText) and pressing <kbd>w</kbd> will open them in a new window.

### Close FileBrowser when files have been opened
Add the following code in your user key bindings file:

```json
{
  "keys": ["enter"],
  "command": "dired_select", "args": {"and_close": true},
  "context": [
    { "key": "selector", "operator": "equal", "operand": "text.dired" },
    { "key": "setting.dired_rename_mode", "operand": false }
  ]
}
```

### Jump List & Jump Points
#### Adding Jump Points
While in *Browse Mode*, you can press <kbd>P</kbd>(Shift + p) to add the current directory to your
*Jump List*, we call it a *Jump Point*. It's like Bookmarks or Favorites in other file managers.

#### Viewing Jump List
There are several ways to view your Jump list:

##### Jump List in a Quick Panel in Browse Mode
While in *Browse Mode*, you can press <kbd>p</kbd> to view the *Jump List* in a Sublime quick panel.

![SublimeFileBrowser Jump List is quick panel](http://cl.ly/image/132X1K0C0P0h/Screen%20Shot%202015-01-25%20at%203.49.42%20pm.png)

**NOTE**: This command does NOT create a new window or project. it lets you jump quickly to a
          particular location.

##### Jump List in a Quick Panel from anywhere
Bring up *Command Palette* and search for `Browse Mode: Jump List Quick Panel` (typing `bmq` should
find it for you).
If you want to save some key stokes you can add the following code in your user key bindings file:

```json
{
  "keys": ["f3"],
  "command": "dired_jump",
  "args": { "new_window": true }
}
```

You can change `f3` in the above code to your custom keyboard shortcut.

**NOTE**: This command creates a new window and open that directory in Sublime with a Browse Mode view.
          The view opens as a left sidebar by default. To change it add `dired_open_on_jump` to your
          user settings file (`Preferences` → `Package Settings` → `FileBrowser` → `Settings — User`).
          Set it to `"right"` to open the view as sidebar on the right side of the window or
          to `true` to fill all space. A value of `false` will prevent any view to open when jumping.  
          To open the directory in the same window call the command with `false`.
          To keep the current window if it is empty call the command with `"auto"`
          and edit your user settings with `"dired_smart_jump": true`.

##### Jump List View
Bring up *Command Palette* and search for `Browse Mode: Jump List` (typing `bmj` should find it for
you). This command will open a *Jump List View* that looks like this:

![SublimeFileBrowser Jump List View](http://cl.ly/image/1e3W1c07311Y/Screen%20Shot%202015-01-25%20at%203.56.45%20pm.png)

If you want to save some key stokes you can add the following code in your user key bindings file:

```json
{ "keys": ["f3"], "command": "dired_jump_list" }
```

You can change `f3` in the above code to your custom keyboard shortcut.
Jump List View can be browsed using the <kbd>up</kbd>/<kbd>down</kbd> or <kbd>j</kbd>/<kbd>k</kbd>.
Pressing <kbd>enter</kbd> on a jump point will open it in a new window with a Browse Mode view as sidebar or what was configured with `dired_open_on_jump`. Empty windows will be reused if `dired_smart_jump` is set to `true` in your user settings.

##### Jump List in a new empty window e.g. Hijacking (ST3 only)
You can also configure FileBrower to automatically open *Jump List View*  in new empty windows.
That is when you run the `new_window` command (through menu or using shortcuts) or when SublimeText
starts and there's no previous windows open.
To do this you need to add the code below to your user settings file (`Preferences` →
`Package Settings` → `FileBrowser` → `Settings — User`)

```json
{ "dired_hijack_new_window": "jump_list" }
```

#### Edit/Delete Jump points
When you are in *Jump List View* pressing <kbd>P</kbd> (Shift + p) allow you to rename or delete
(by clearing the name) the jump point that is currently highlighted.

When a jump point is opened in *Browse Mode* pressing <kbd>P</kbd> will also do the same.

**NOTE**: When a jump point is opened in *Browse Mode* the path in the header is prefixed with name
of the jump point.

### Hidden files
By default, FileBrowser shows all files in the browsed directory. Pressing <kbd>h</kbd> toggles the
display of hidden files. For all platforms, any file that starts with a `.` is considered hidden;
additionally, on Windows, files that have the hidden attribute set are also considered hidden.

To set FileBrowser to hide hidden files by default, add the following to your settings:

``` json
{ "dired_show_hidden_files": false }
```

You can also customize the patterns used to determine if a file should be hidden with the
`dired_hidden_files_patterns` setting, which should be either a single pattern string or a list of
such patterns:

``` json
{ "dired_hidden_files_patterns": [".*", "__pycache__", "*.pyc"] }
```

### VCS integration
In case `git status`(or `hg status`) returns a colorable output in current directory, the modified
and untracked files will be designated by orange and green icons respectively.
You can use setting `"vcs_color_blind": true` — untracked files will get vertical line on left side
of their icons, modified files will get horizontal line under their icons.
If Git (or HG) is not presented in your `PATH` you may set `git_path` (resp `hg_path`) setting (see
example in default settings file).


### Hijacking a new empty window (ST3 only)
**FileBrowser** can hijack new empty windows and show you a *Browse Mode* or *Jump List View*. That
is when you run the `new_window` command (through menu or using shortcuts) or when SublimeText
starts and there's no previous windows open.

This feature is only available for ST3 and is disabled by default. You can activate it by setting
`dired_hijack_new_window` to `"jump_list"` or `"dired"` in your user settings file (`Preferences` →
`Package Settings` → `FileBrowser` → `Settings — User`).

To disable this feature set it back to `false` or remove if from your user settings file.

``` json
{ "dired_hijack_new_window": "jump_list"}
```


### Using Mouse!
We believe keeping your hands on keyboard and not moving them away to reach the mouse or track-pad
will increase your productivity. Despite this, there might be situations where using a mouse to
click on a file is easier or you might be in transition to becoming a keyboard ninja and still
prefer the mouse by habit.
For these situations, you can just double click a file or directory to open them.
Although we stand firm with our belief, we're *liberals*! :)

## Tweaking Look and Feel

#### Customizing UI Elements
If you don't like `⠤` symbol and want to hide it (then you should use keyboard binding `backspace`
to go to parent directory) you can do it in your user settings file (`Preferences` →
`Package Settings` → `FileBrowser` → `Settings — User`) and paste the code below:

``` json
{ "dired_show_parent": false }
```

If you want to see header (underlined full path) on top of file list:

```json
{ "dired_header": true }
```

If you want to see full path in tab title and thus in window title if tab is focused:

```json
{ "dired_show_full_path": true }
```

#### Changing color scheme
If you don't like colors used in FileBrowser just copy
[this file](https://github.com/aziz/SublimeFileBrowser/blob/master/dired.hidden-tmTheme)
to your User directory, change colors and paste the code below in your user settings file:

``` json
{ "color_scheme": "Path to your custom color scheme file. e.g. Packages/User/custom_dired.hidden-tmTheme" }
```

#### Changing font
Changing the font of sidebar in SublimeText is not that easy! not if you're using FileBrowser as
your sidebar. Since it is just a normal Sublime view with a special syntax, you can change the font
to whatever font that's available on your system.

To do that, add the code below (don't forget to change the font name!) to user settings file
(`Preferences` → `Package Settings` → `FileBrowser` → `Settings — User`).

``` json
{ "font_face": "comic sans" }
```

#### Changing font size
Normally you want the FileBrowser to use a smaller font compared to your normal views. It helps you
see more content and also prevents any font size changes when you make your normal view font bigger
or smaller.

You can change the font size by adding the code below to user settings file (`Preferences` →
`Package Settings` → `FileBrowser` → `Settings — User`).

``` json
{ "font_size": 13 }
```

#### Changing nested directories indentation
The amount of indentation for nested directories is controlled by `tab_size`. By default FileBrowser
is using a tab_size of 3 but you can customize it in your user settings file (`Preferences` →
`Package Settings` → `FileBrowser` → `Settings — User`).

## General tip for Windows users
DirectWrite rendering gives better Unicode support and better font appearance overall, to enable it
add following setting into `Preferences` → `Settings — User`:

``` json
{ "font_options": ["directwrite"] }
```

## Credit

This is a fork of the awesome [dired plugin](https://github.com/mkleehammer/dired) by
[Michael Kleehammer](https://github.com/mkleehammer)

#### License
See the LICENSE file
