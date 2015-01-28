
# FileBrowser for SublimeText

Ditch sidebar and browse your files in a normal tab with keyboard, like a pro!

![SublimeFileBrowser Screenshot](http://cl.ly/image/2y1R143k3J1n/Screen%20Shot%202015-01-28%20at%208.22.56%20pm.png)

You can also use it as a sidebar that you can put on right or left side

![SublimeFileBrowser Screenshot2](http://cl.ly/image/2Y37412n351x/Screen%20Shot%202015-01-28%20at%208.33.28%20pm.png)

## Installation

You can install via [Sublime Package Control](http://wbond.net/sublime_packages/package_control)  
Or you can clone this repo into your SublimeText Packages directory and rename it to `FileBrowser`

## Commands and Keybindings

This plugin does not add any keybindings for opening a new tab in *Browse Mode*. Although, the commands to do that are available in *Command Palette* but it is recommended to bind <kbd>F1</kbd> to open the current file directory in *Browse Mode* with this piece of code (that you can add to your `Key Bindings - User` file):

``` json
{
  "keys": ["f1"],
  "command": "dired",
  "args": { "immediate": true }
}
```

You also can use optional arguments to tweak behavior:

* `"single_pane": true` — always use a single File Browser view, i.e. prefer to reuse existing one rather than create a new.
* `"other_group": "left"` (or `"right`) — open FileBrowser in other group, i.e. like sidebar; if you use `"left"` then all other tabs from left group will be moved into the right one.
* `"project": true` — always prefer project's directory(s) rather than path of current view.

You can mix these arguments as you like (perhaps, even bind several shortcuts for different cases); e.g. to completely mimic sidebar, it would be:

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
##### Navigation Shortcuts
| Command                                               | Shortcut                                   |
| :---------------------------------------------------- | :----------------------------------------- |
| Toggle mark                                           | <kbd>m</kbd>                               |
| Toggle mark and move down                             | <kbd>shift+↓</kbd>                         |
| Toggle mark and move up                               | <kbd>shift+↑</kbd>                         |
| Toggle all marks                                      | <kbd>t</kbd>                               |
| Unmark all                                            | <kbd>u</kbd>                               |
| Mark by extension                                     | <kbd>\*</kbd>                              |
| Go to parent directory                                | <kbd>backspace</kbd>                       |
| Go to directory                                       | <kbd>g</kbd>                               |
| Go to first                                           | <kbd>⌘+↑</kbd> or <kbd>ctrl+home</kbd>     |
| Go to last                                            | <kbd>⌘+↓</kbd> or <kbd>ctrl+end</kbd>      |
| Move to previous                                      | <kbd>k</kbd> or <kbd>↑</kbd>               |
| Move to next                                          | <kbd>j</kbd> or <kbd>↓</kbd>               |
| Expand directory                                      | <kbd>→</kbd>                               |
| Collapse directory                                    | <kbd>←</kbd>                               |
| Jump to                                               | <kbd>/</kbd>                               |
| Quick jump to directory                               | <kbd>p</kbd>                               |
| Find in files                                         | <kbd>s</kbd>                               |

##### Action Shortcuts
| Command                                               | Shortcut                                   |
| :---------------------------------------------------- | :----------------------------------------- |
| Open file/view directory                              | <kbd>o</kbd>                               |
| Open file in another group                            | <kbd>enter</kbd>                           |
| Preview file in another group                         | <kbd>shift+enter</kbd>                     |
| Open all marked items in new tabs                     | <kbd>⌘+enter</kbd> / <kbd>ctrl+enter</kbd> |
| Open in Finder/File Explorer                          | <kbd>\\</kbd>                              |
| Open in new window                                    | <kbd>w</kbd>                               |
| Refresh view                                          | <kbd>r</kbd>                               |
| Help page                                             | <kbd>?</kbd>                               |
| Rename                                                | <kbd>R</kbd>                               |
| Move                                                  | <kbd>M</kbd>                               |
| Delete                                                | <kbd>D</kbd>                               |
| Send to trash                                         | <kbd>S</kbd>                               |
| Create directory                                      | <kbd>cd</kbd>                              |
| Create file                                           | <kbd>cf</kbd>                              |
| Create/Edit/Remove jump point                         | <kbd>P</kbd>                               |
| Toggle hidden files                                   | <kbd>h</kbd>                               |
| Toggle add directory to project                       | <kbd>f</kbd>                               |
| Set current directory as only one for the project     | <kbd>F</kbd>                               |
| Quicklook for Mac or open in default app on other OSs | <kbd>space</kbd>                           |

##### *Rename Mode* Shortcuts
| Command          | Shortcut           |
| :--------------- | :----------------- |
| Apply changes    | <kbd>enter</kbd>   |
| Discard changes  | <kbd>escape</kbd>  |

## Usage

### Selecting Files and Directories
You can select files and/or directories by marking them with <kbd>m</kbd>, or <kbd>Shift + up/down</kbd> or just use SublimeText multiple cursor feature and extend your cursor to the line that has those files/directories.

### Search
Besides incremental search available by <kbd>/</kbd>, you also may use build-in "Goto Symbol…" (<kbd>⌘+r</kbd> or <kbd>ctrl + r</kbd>) for fuzzy search.

### "Find in Files…" integration
Press <kbd>s</kbd> to summon "Find in Files…" panel — if you've marked some files they will fill *Where* field, otherwise it will be filled by current directory path.

### Rename Mode
The rename command puts the view into **rename mode**. The view is made editable so files can be renamed directly in the view using all of your SublimeText tools: multiple cursors, search and replace, etc.

After you are done with editing press <kbd>enter</kbd> to commit your changes or <kbd>escape</kbd> to cancel them.

### Open in new window
Selecting a couple of files and/or directories (either by marking them or using the normal multiple cursor feature of SublimeText) and pressing <kbd>w</kbd> will open them in a new window.

### Close FileBrowser when files have been opened
Add the following code in your user key bindings file:

```json
{
  "keys": ["o"],
  "command": "dired_select", "args": {"and_close": true},
  "context": [
    { "key": "selector", "operator": "equal", "operand": "text.dired" },
    { "key": "setting.dired_rename_mode", "operand": false }
  ]
}
```

### Jump List & Jump Points
#### Adding Jump Points
While in *Browse Mode*, you can press <kbd>P</kbd>(Shift + p) to add the current directory to your *Jump List*, we call it a *Jump Point*. It's like Bookmarks or Favorites in other file managers. 

#### Viewing Jump List
There are several ways to view your Jump list:

##### Jump List in a Quick Panel in Browse Mode
While in *Browse Mode*, you can press <kbd>p</kbd> to view the *Jump List* in a Sublime quick panel.

![SublimeFileBrowser Jump List is quick panel](http://cl.ly/image/132X1K0C0P0h/Screen%20Shot%202015-01-25%20at%203.49.42%20pm.png)

**NOTE**: This command does NOT create a new window or project. it lets you jump quickly to a particular location. 

##### Jump List in a Quick Panel from anywhere
Bring up *Command Palette* and search for `Browse Mode: Jump List Quick Panel` (typing `bmq` should find it for you).
If you want to save some key stokes you can add the following code in your user key bindings file:

```json
{
  "keys": ["f3"],
  "command": "dired_jump",
  "args": { "new_window": true }
}
```

You can change `f3` in the above code to your custom keyboard shortcut.

**NOTE**: This command creates a new window and open that directory in Sublime. It also opens a Browse Mode view as sidebar.

##### Jump List View
Bring up *Command Palette* and search for `Browse Mode: Jump List` (typing `bmj` should find it for you).
This command will open a *Jump List View* that looks like this:

![SublimeFileBrowser Jump List View](http://cl.ly/image/1e3W1c07311Y/Screen%20Shot%202015-01-25%20at%203.56.45%20pm.png)

If you want to save some key stokes you can add the following code in your user key bindings file:

```json
{ "keys": ["f3"], "command": "dired_jump_list" }
```

You can change `f3` in the above code to your custom keyboard shortcut.
Jump List View can be browsed using the <kbd>up</kbd>/<kbd>down</kbd> or <kbd>j</kbd>/<kbd>k</kbd>. Pressing <kbd>enter</kbd> on a jump point will open it in a new window with a Browse Mode view as sidebar.

##### Jump List in a new empty window e.g. Hijacking (ST3 only)
You can also configure FileBrower to automatically open *Jump List View*  in new empty windows. That is when you run the `new_window` command (through menu or using shortcuts) or when SublimeText starts and there's no previous windows open. 
To do this you need to add the code below to your user syntax specific settings file (`Preferences` → `Package Settings` → `FileBrowser` → `Settings — User`)

```json
{ "dired_hijack_new_window": "jump_list" }
```

#### Edit/Delete Jump points
When you are in *Jump List View* pressing <kbd>P</kbd> (Shift + p) allow you to rename or delete (by clearing the name) the jump point that is currently highlighted. 

When a jump point is opened in *Browse Mode* pressing <kbd>P</kbd> will also do the same. 

**NOTE**: When a jump point is opened in *Browse Mode* the path in the header is prefixed with name of the jump point.


### Hidden files
By default, FileBrowser shows all files in the browsed directory. Pressing <kbd>h</kbd> toggles the display of hidden files. For all platforms, any file that starts with a `.` is considered hidden; additionally, on Windows, files that have the hidden attribute set are also considered hidden.

To set FileBrowser to hide hidden files by default, add the following to your settings:

``` json
{ "dired_show_hidden_files": false }
```

You can also customize the patterns used to determine if a file should be hidden with the `dired_hidden_files_patterns` setting, which should be either a single pattern string or a list of such patterns:

``` json
{ "dired_hidden_files_patterns": [".*", "__pycache__", "*.pyc"] }
```

### Git integration
In case `git status` returns a colorable output in current directory, the modified and untracked files will be designated by orange and green icons respectively.  
You can use setting `"vcs_color_blind": true` — untracked files will get vertical line on left side of their icons, modified files will get horizontal line under their icons.  
If Git is not presented in your `PATH` you may set `git_path` setting (see example in default settings file).


### Hijacking a new empty window (ST3 only)
**FileBrowser** can hijack new empty windows and show you a *Browse Mode* or *Jump List View*. That is when you run the `new_window` command (through menu or using shortcuts) or when SublimeText starts and there's no previous windows open. 

This feature is only available for ST3 and is disabled by default. You can activate it by setting `dired_hijack_new_window` to `"jump_list"` or `"dired"` in your user syntax specific settings file (`Preferences` → `Package Settings` → `FileBrowser` → `Settings — User`).

To disable this feature set it back to `false` or remove if from your user settings file.

``` json
{ "dired_hijack_new_window": "jump_list"}
```


## Tweaking Look and Feel

#### Customizing UI Elements
If you don't like `⠤` symbol and want to hide it (then you should use keyboard binding `backspace` to go to parent directory) you can do it in your user syntax specific settings file (`Preferences` → `Package Settings` → `FileBrowser` → `Settings — User`) and paste the code below:

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
If you don't like colors used in FileBrowser just copy [this file](https://github.com/aziz/SublimeFileBrowser/blob/master/dired.hidden-tmTheme) to your User directory, change colors and paste the code below in your user syntax specific settings file:

``` json
{ "color_scheme": "Path to your custom color scheme file. e.g. Packages/User/custom_dired.hidden-tmTheme" }
```

#### Changing font
Changing the font of sidebar in SublimeText is not that easy! not if you're using FileBrowser as your sidebar. Since it is just a normal Sublime view with a special syntax, you can change the font to whatever font that's available on your system. 

To do that, add the code below (don't forget to change the font name!) to user syntax specific settings file (`Preferences` → `Package Settings` → `FileBrowser` → `Settings — User`).

``` json
{ "font_face": "comic sans" }
```

#### Changing font size
You normally want the FileBrowser to use a smaller font compared to your normal views. It helps you 
view more content and also prevent any font size changes when you make your normal views' font bigger or smaller. 

You can change the font size by adding the code below to user syntax specific settings file (`Preferences` → `Package Settings` → `FileBrowser` → `Settings — User`).

``` json
{ "font_size": 13 }
```

## General tip for Windows users
DirectWrite rendering gives better Unicode support and better font appearance overall, to enable it add following setting into `Preferences` → `Settings — User`:

``` json
{ "font_options": ["directwrite"] }
```

## Credit

This is a fork of the awesome [dired plugin](https://github.com/mkleehammer/dired) by [Michael Kleehammer](https://github.com/mkleehammer)

#### License
See the LICENSE file
