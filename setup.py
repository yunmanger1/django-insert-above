#!/usr/bin/env python
import os
from distutils.core import setup

def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(name='django-insert-above',
    version='1.0.1',
    description='These django templatetags is a hack making possible to insert "content" in some (maybe above the current or parent template) places.',
    author='German Ilyin',
    author_email='germanilyin@gmail.com',
    url='https://github.com/yunmanger1/django-insert-above/',
    license='WTFPL',
    long_description=read('README'),
    packages=['insert_above','insert_above.templatetags'],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Topic :: Utilities",
        "Environment :: Plugins",
        "Framework :: Django",
        "Intended Audience :: Developers",
        "License :: Freeware",
        "Programming Language :: Python :: 2.6",
    ],
)     
