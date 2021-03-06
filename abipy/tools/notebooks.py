"""Tools for ipython notebooks."""
from __future__ import print_function, division, unicode_literals, absolute_import


def print_source_in_module(function, module):
    """
    For use inside an IPython notebook: given a module and a function, print the source code.

    Based on:
        http://stackoverflow.com/questions/20665118/how-to-show-source-code-of-a-package-function-in-ipython-notebook
    """
    from inspect import getmembers, isfunction, getsource
    from pygments import highlight
    from pygments.lexers import PythonLexer
    from pygments.formatters import HtmlFormatter
    from IPython.core.display import HTML

    internal_module = __import__(module)
    internal_functions = dict(getmembers(internal_module, isfunction))
    return HTML(highlight(getsource(internal_functions[function]), PythonLexer(), HtmlFormatter(full=True)))


def print_source(function):
    """
    For use inside an IPython notebook: given a function, print the source code.
    """
    from inspect import getsource
    from pygments import highlight
    from pygments.lexers import PythonLexer
    from pygments.formatters import HtmlFormatter
    from IPython.core.display import HTML

    return HTML(highlight(getsource(function), PythonLexer(), HtmlFormatter(full=True)))


def ipw_listdir(top=".", recurse=True, widget_type="dropdown"):
    """
    Return an ipython widget listing all the files located within the directory `top`
    that can be inspected with `abiopen`. The user can select the file in the widget
    and print info on the corresponding file inside the notebook.

    Args:
        top: Initial directory.
        recurse: False to ignore directories within `top`.
        widget_type: Specify the widget to create. Possible values in:
            ["tooglebuttons", "dropdown", "radiobuttons"]
    """
    from abipy import abilab
    from IPython.display import display, clear_output
    import ipywidgets as ipw

    # Select the widget class from widget_type
    d = dict(
        tooglebuttons=ipw.ToggleButtons,
        dropdown=ipw.Dropdown,
        radiobuttons=ipw.RadioButtons,
    )
    try:
        widget_class = d[widget_type]
    except KeyError:
        raise KeyError("Invalid `widget_type`: %s, Choose among: %s" % (widget_type, str(list(d.keys()))))

    def on_value_change(change):
        """Callback"""
        clear_output()
        path = change["new"]
        #print(change)
        with abilab.abiopen(path) as abifile:
            print(abifile)
            #display(abifile)

    # Get dict: dirname --> list_of_files supported by abiopen.
    dir2files = abilab.dir2abifiles(top, recurse=recurse)
    children = []
    for dirname, files in dir2files.items():
        w = widget_class(options=files, description="%s:" % dirname)
        # TODO: Should register the callback of "selected" but I didn't find the event type!
        w.observe(on_value_change, names='value', type="change")
        children.append(w)
    box = ipw.VBox(children=children)

    return display(box)
