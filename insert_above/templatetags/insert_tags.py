"""
This program is free software. It comes without any warranty, to
the extent permitted by applicable law. You can redistribute it
and/or modify it under the terms of the Do What The Fuck You Want
To Public License, Version 2, as published by Sam Hocevar. See
http://sam.zoy.org/wtfpl/COPYING for more details.
"""

from django import template
from django.conf import settings
from django.template import loader_tags
from django.utils.encoding import force_unicode
from django.utils.safestring import mark_safe
import time
from django.template.base import Variable
from django import forms
from django.utils.datastructures import SortedDict
register = template.Library()

try:
    from common import logwrapper
    log = logwrapper.defaultLogger(__file__)
except ImportError:
    import logging
    log = logging.getLogger(__name__)

INSERT_TAG_KEY = 'insert-demands'
DEBUG = getattr(settings, 'IA_DEBUG', False)
MEDIA_URL = getattr(settings, 'IA_MEDIA_PREFIX', None)
if MEDIA_URL is None:
    MEDIA_URL = getattr(settings, 'STATIC_URL', None)
if MEDIA_URL is None:
    MEDIA_URL = getattr(settings, 'MEDIA_URL', None)
if MEDIA_URL is None:
    MEDIA_URL = '/media/'
USE_MEDIA_PREFIX = getattr(settings, 'IA_USE_MEDIA_PREFIX', True)
JS_FORMAT = getattr(settings, 'IA_JS_FORMAT', "<script type='text/javascript' src='{URL}'></script>")
CSS_FORMAT = getattr(settings, 'IA_CSS_FORMAT', "<link rel='stylesheet' href='{URL}' type='text/css' />")

if hasattr(settings, 'IA_MEDIA_EXTENSION_FORMAT_MAP'):
    MEDIA_EXTENSION_FORMAT_MAP = settings.IA_MEDIA_EXTENSION_FORMAT_MAP
else:
    # by convention key must be 3 characters length. This helps to optimize lookup process
    MEDIA_EXTENSION_FORMAT_MAP = {
        'css' : CSS_FORMAT,
        '.js' : JS_FORMAT,
    }

def render_media(extension, ctx):
    """
    Renders media format. Used in media container.
    """
    fmt = MEDIA_EXTENSION_FORMAT_MAP[extension]
    return fmt.format(**ctx)

def get_from_context_root(context, KEY):
    """
    Gets or creates dictinoary in root context.
    """
    if not KEY in context.dicts[0]:
        context.dicts[0].update({KEY : {}})
    return context.dicts[0].get(KEY)

def add_render_time(context, dt):
    """
    Adds value to root context, which will be used
    later in insert handler node.
    """
    cache = get_from_context_root(context, INSERT_TAG_KEY)
    t = cache.get('DEBUG_TIME', 0) + dt
    cache.update({'DEBUG_TIME': t})

def get_render_time(context):
    cache = get_from_context_root(context, INSERT_TAG_KEY)
    t = cache.get('DEBUG_TIME', 0)
    return t

def consider_time(f):
    """
    Decorator used to calculate 
    how much time was spent on rendering
    "insert_above" tags.
    """
    def nf(obj, context, *args, **kwargs):
        t = time.time()
        result = f(obj, context, *args, **kwargs)
        dt = time.time() - t
        add_render_time(context, dt)
        return result
    if DEBUG:
        return nf
    return f

class OrderedItem(object):
    """
    String items all over the templates must be
    rendered in the same order they were encountered.
    """
    order = 0

    def __init__(self, item):
        cur = OrderedItem.order
        self.item, self.order = item, cur
        OrderedItem.order = cur + 1

    def __cmp__(self, o):
        if self.item == o.item:
            return 0
        return self.order - o.order

    def __unicode__(self):
        return self.item

    def __hash__(self):
        return self.item.__hash__()

    def __str__(self):
        return self.__unicode__()

class InsertHandlerNode(template.Node):
    #must_be_first = True

    def __init__(self, nodelist, *args, **kwargs):
        super(InsertHandlerNode, self).__init__(*args, **kwargs)
        self.nodelist = nodelist
        self.blocks = dict([(n.name, n) for n in nodelist.get_nodes_by_type(template.loader_tags.BlockNode)])

    def __repr__(self):
        return '<MediaHandlerNode>'

    def render_nodelist(self, nodelist, context):
        bits = []
        medias = []
        index = 0
        for node in nodelist:
            if isinstance(node, ContainerNode):
                node.index = index
                bits.append('')
                medias.append(node)
            elif isinstance(node, template.Node):
                bits.append(nodelist.render_node(node, context))
            else:
                bits.append(node)
            index += 1
        for node in medias:
            bits[node.index] = nodelist.render_node(node, context)
        if DEBUG:
            log.debug("spent {0:.6f} ms on insert_tags".format(get_render_time(context)))
        return mark_safe(''.join([force_unicode(b) for b in bits]))

    def render(self, context):
        if loader_tags.BLOCK_CONTEXT_KEY not in context.render_context:
            context.render_context[loader_tags.BLOCK_CONTEXT_KEY] = loader_tags.BlockContext()
        block_context = context.render_context[loader_tags.BLOCK_CONTEXT_KEY]

        # Add the block nodes from this node to the block context
        block_context.add_blocks(self.blocks)
        return self.render_nodelist(self.nodelist, context)
#        return self.nodelist.render(context)

class InsertNode(template.Node):
    def __init__(self, container_name, insert_string = None, subnodes = None, *args, **kwargs):
        """
        Note: `self.container_name, self.insert_line, self.subnodes` must not be changed during 
        `render()` call. Method `render()` may be called multiple times. 
        """
        super(InsertNode, self).__init__(*args, **kwargs)
        self.container_name, self.insert_line, self.subnodes = container_name, insert_string, subnodes
        self.index = None
        self.prev_context_hash = None

    def __repr__(self):
        return "<Media Require Node: %s>" % (self.insert_line)

    def push_media(self, context):
        if self.prev_context_hash == context.__hash__():
            if DEBUG:
                log.debug('same context: {0} == {1}'.format(self.prev_context_hash, context.__hash__()))
            return
        self.prev_context_hash = context.__hash__()
        cache = get_from_context_root(context, INSERT_TAG_KEY)
        reqset = cache.get(self.container_name, None)
        if not reqset:
            reqset = []
            cache[self.container_name] = reqset
        insert_content = None
        if self.insert_line == None:
            if self.subnodes == None:
                raise AttributeError('insert_line or subnodes must be specified')
            insert_content = self.subnodes.render(context)
        else:
            if self.subnodes != None:
                raise AttributeError('insert_line or subnodes must be specified, not both')
            var = True
            insert_content = Variable(self.insert_line).resolve(context)
        reqset.append(OrderedItem(insert_content))

    @consider_time
    def render(self, context):
        self.push_media(context)
        return ''

class ContainerNode(template.Node):
    def __init__(self, name, *args, **kwargs):
        super(ContainerNode, self).__init__(*args, **kwargs)
        self.name = name

    def __repr__(self):
        return "<Container Node: %s>" % (self.name)

    @consider_time
    def render(self, context):
        reqset = get_from_context_root(context, INSERT_TAG_KEY).get(self.name, None)
        if not reqset:
            return ''
        items = reqset
        #items.sort()
        return "\n".join([x.__unicode__() for x in items])

def media_tag(url, **kwargs):
    """
    Usage: {{ url|media_tag }}
    Simply wraps media url into appropriate HTML tag.
    
    Example: {{ "js/ga.js"|media_tag }} 
    The result will be <script type='text/javascript' src='/static/js/ga.js'></script>
    
    Last 3 characters of url define which 
    format string from MEDIA_EXTENSION_FORMAT_MAP will be used.  
    """

    url = url.split('\n')[0].strip()
    ext = url[-3:]
    full = url.startswith('http://') or url.startswith('https://')
    if USE_MEDIA_PREFIX and not full:
        link = '{0}{1}'.format(MEDIA_URL, url)
    else:
        link = url
    return render_media(ext, {'URL' : link })


def fetch_urls(item, url_set):
    if isinstance(item, forms.Form):
        item = getattr(item, 'media', None)
        if item is None:
            return

    if isinstance(item, forms.Media):
        css, js = None, None
        css = getattr(item, '_css', {})
        js = getattr(item, '_js', [])
        if css:
            for key, list in css.items():
                for url in list:
                    url_set[url] = key
        if js:
            for url in js:
                url_set[url] = 1
    elif isinstance(item, (str, unicode)):
        url_set[item] = 1

class MediaContainerNode(ContainerNode):

    @consider_time
    def render(self, context):
        reqset = get_from_context_root(context, INSERT_TAG_KEY).get(self.name, None)
        if not reqset:
            return ''
        items = reqset
        items.sort()
        url_set = SortedDict()
        for obj in items:
            fetch_urls(obj.item, url_set)
        result = [media_tag(key) for key, value in url_set.items()]
        if result:
            return "\n".join(result)
        return ''

@register.tag
def insert_handler(parser, token):
    """
    This is required tag for using insert_above tags. It must be 
    specified in the very "base" template and at the very beginning.
    
    Simply, this tag controls the rendering of all tags after it. Note
    that if any container node goes before this tag it won't be rendered
    properly.
    
    {% insert_handler %}
    """
    bits = token.split_contents()
    if len(bits) != 1:
        raise template.TemplateSyntaxError("'%s' takes no arguments" % bits[0])
    nodelist = parser.parse()
    if nodelist.get_nodes_by_type(InsertHandlerNode):
        raise template.TemplateSyntaxError("'%s' cannot appear more than once in the same template" % bits[0])
    return InsertHandlerNode(nodelist)

@register.tag
def container(parser, token):
    """
    This tag specifies some named block where items will be inserted
    from all over the template.
    
    {% container js %}
    
    js - here is name of container
    
    It's set while inserting string
     
    {% insert_str js "<script src='js/jquery.js' type=...></script>" %}
    """
    bits = token.split_contents()
    if len(bits) != 2:
        raise template.TemplateSyntaxError("'%s' takes one argument" % bits[0])
    return ContainerNode(bits[1])

@register.tag
def media_container(parser, token):
    """
    This tag is an example of how ContainerNode might be overriden.
    
    {% media_container js %}
    
    js - here is name of container
    
    It's set while inserting string
     
    {% insert_str js "js/jquery.js" %}
    {% insert_str js "css/style.css" %}
    
    Here only media urls are set. MediaContainerNode will identify
    by last 3 characters and render on appropriate template.
    
    By default only '.js' and 'css' files are rendered. It can be extended
    by setting MEDIA_EXTENSION_FORMAT_MAP variable in settings.
    
    """
    bits = token.split_contents()
    if len(bits) != 2:
        raise template.TemplateSyntaxError("'%s' takes one argument" % bits[0])
    return MediaContainerNode(bits[1])

@register.tag
def insert_str(parser, token):
    """
    This tag inserts specified string in containers.
    
    Usage:     {% insert_str container_name string_to_insert %}
    
    Example: {% insert_str js "<script src="media/js/jquery.js"></script>" %}
    
    """
    bits = token.split_contents()
    if len(bits) != 3:
        raise template.TemplateSyntaxError("'%s' takes two arguments" % bits[0])
    return InsertNode(bits[1], bits[2])

@register.tag
def insert_form(parser, token):
    """
    This tag inserts specified string in containers.
    
    Usage:     {% insert_str container_name form %}
    
    Example: {% insert_form js form %}
    
    """
    bits = token.split_contents()
    if len(bits) != 3:
        raise template.TemplateSyntaxError("'%s' takes two arguments" % bits[0])
    return InsertNode(bits[1], bits[2])


@register.tag
def insert(parser, token):
    """
    This tag with end token allows to insert not only one string.
    
    {% insert js %}
    <script>
    $(document).ready(function(){
        alert('hello, {{ user }}!');
    });
    </script>
    {% endinsert %}
    """
    subnodes = parser.parse(('endinsert',))
    parser.delete_first_token()
    bits = token.contents.split()
    if len(bits) < 2:
        raise template.TemplateSyntaxError(u"'%r' tag requires 2 arguments." % bits[0])
    return InsertNode(bits[1], subnodes = subnodes)

register.filter('media_tag', media_tag)
