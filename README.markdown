Installation
------------

1. (required) add 'insert_above' in INSTALLED_APP in your settings.py

2. (optional) add these two lines of code somewhere in your project where
they will run for sure. For example in urls.py

~~~~
from django.template.loader import add_to_builtins
add_to_builtins('insert_above.templatetags.insert_tags')
~~~~
