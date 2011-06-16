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
register = template.Library()

try:
    from common import logwrapper
    log = logwrapper.defaultLogger(__file__)
except ImportError:
    import logging
    log = logging.getLogger(__name__)

INSERT_TAG_KEY = 'insert-demands'
DEBUG = settings.DEBUG
MEDIA_URL = settings.MEDIA_URL
if hasattr(settings,'JS_TEMPLATE_STR'):
    JS_TEMPLATE_STR = settings.JS_TEMPLATE_STR
else:
    JS_TEMPLATE_STR = "<script type='text/javascript' src='{{ URL }}'></script>"

if hasattr(settings,'CSS_TEMPLATE_STR'):
    CSS_TEMPLATE_STR = settings.CSS_TEMPLATE_STR
else:
    CSS_TEMPLATE_STR = "<link rel='stylesheet' href='{{ URL }}' type='text/css' />"
    
if hasattr(settings,'MEDIA_EXTENSION_TEMPLATE_STRING_MAP'):
    MEDIA_EXTENSION_TEMPLATE_STRING_MAP = settings.MEDIA_EXTENSION_TEMPLATE_STRING_MAP
else:
    # by convention key must be 3 characters length. This helps to optimize lookup process
    MEDIA_EXTENSION_TEMPLATE_STRING_MAP = {
        'css' : CSS_TEMPLATE_STR,
        '.js' : JS_TEMPLATE_STR,
    }
    
MEDIA_EXTENSION_TEMPLATE_MAP = {}

def get_media_template(extension):    
    """
    Gets or creates template instance for 
    media file extension.
    """     
    if not extension in MEDIA_EXTENSION_TEMPLATE_MAP:
        if not extension in MEDIA_EXTENSION_TEMPLATE_STRING_MAP:    
            raise AttributeError('invalid extension: {0}'.format(extension))
        tpl = template.Template(MEDIA_EXTENSION_TEMPLATE_STRING_MAP[extension])
        MEDIA_EXTENSION_TEMPLATE_MAP[extension] = tpl
    return MEDIA_EXTENSION_TEMPLATE_MAP[extension]

def render_media_template_to_string(extension, ctx):
    """
    Renders media template to string. Used in media container.
    """     
    tpl = get_media_template(extension)
    return tpl.render(template.Context(ctx))
    
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
        result = f(obj, context, *args,**kwargs)
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
    def __init__(self, container_name, insert_str=None, nodelist=None, *args, **kwargs):
        super(InsertNode, self).__init__(*args, **kwargs)
        self.container_name, self.insert_str, self.nodelist = container_name, insert_str, nodelist
        self.index = None

    def __repr__(self):
        return "<Media Require Node: %s>" % (self.insert_str)
    
    def push_media(self, context):
        cache = get_from_context_root(context, INSERT_TAG_KEY)
        reqset = cache.get(self.container_name, None)
        if not reqset:
            reqset = set()
            cache[self.container_name] = reqset
        if self.insert_str is None:
            if self.nodelist is None:
                raise AttributeError('insert_str or nodelist must be specified')
            self.insert_str = self.nodelist.render(context)
        else:
            if self.insert_str.startswith('"'):
                self.insert_str = self.insert_str[1:]
            if self.insert_str.endswith('"'):
                self.insert_str = self.insert_str[:-1]
        reqset.add(OrderedItem(self.insert_str))
    
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
        reqset = get_from_context_root(context, INSERT_TAG_KEY).get(self.name,None)
        if not reqset:
            return '' 
        items = list(reqset)
        items.sort()
        return "\n".join([x.__unicode__() for x in items])

class MediaContainerNode(ContainerNode):
  
    @consider_time
    def render(self, context):
        reqset = get_from_context_root(context, INSERT_TAG_KEY).get(self.name,None)
        if not reqset:
            return '' 
        items = list(reqset)
        items.sort()
        urls = [x.__unicode__().split('\n')[0].strip() for x in items]
        result = []
        for url in urls:
            ext = url[-3:]
            result.append(render_media_template_to_string(ext, {'URL' : '{0}{1}'.format(MEDIA_URL, url)}))
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
    by setting MEDIA_EXTENSION_TEMPLATE_STRING_MAP variable in settings.
    
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
    nodelist = parser.parse(('endinsert',))
    parser.delete_first_token()
    bits = token.contents.split()
    if len(bits) < 2:
        raise template.TemplateSyntaxError(u"'%r' tag requires 2 arguments." % bits[0])
    return InsertNode(bits[1], nodelist = nodelist)
