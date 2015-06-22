"""
INLINE PATTERNS
=============================================================================

Inline patterns such as *emphasis* are handled by means of auxiliary
objects, one per pattern.  Pattern objects must be instances of classes
that extend markdown.Pattern.  Each pattern object uses a single regular
expression and needs support the following methods:

    pattern.getCompiledRegExp() # returns a regular expression

    pattern.handleMatch(m) # takes a match object and returns
                           # an ElementTree element or just plain text

All of python markdown's built-in patterns subclass from Pattern,
but you can add additional patterns that don't.

Also note that all the regular expressions used by inline must
capture the whole block.  For this reason, they all start with
'^(.*)' and end with '(.*)!'.  In case with built-in expression
Pattern takes care of adding the "^(.*)" and "(.*)!".

Finally, the order in which regular expressions are applied is very
important - e.g. if we first replace http://.../ links with <a> tags
and _then_ try to replace inline html, we would end up with a mess.
So, we apply the expressions in the following order:

* escape and backticks have to go before everything else, so
  that we can preempt any markdown patterns by escaping them.

* then we handle auto-links (must be done before inline html)

* then we handle inline HTML.  At this point we will simply
  replace all inline HTML strings with a placeholder and add
  the actual HTML to a hash.

* then inline images (must be done before links)

* then bracketed links, first regular then reference-style

* finally we apply strong and emphasis
"""

from __future__ import absolute_import
from __future__ import unicode_literals
from . import util
from . import odict
import re
try:  # pragma: no cover
    from html import entities
except ImportError:  # pragma: no cover
    import htmlentitydefs as entities


def build_inlinepatterns(md, **kwargs):
    """ Build the default set of inline patterns for Markdown. """
    inlinePatterns = odict.OrderedDict()
    inlinePatterns["backtick"] = BacktickPattern(BACKTICK_RE)
    inlinePatterns["escape"] = EscapePattern(ESCAPE_RE, md)
    inlinePatterns["reference"] = ReferencePattern(REFERENCE_RE, md)
    inlinePatterns["link"] = LinkPattern(LINK_RE, md)
    inlinePatterns["image_link"] = ImagePattern(IMAGE_LINK_RE, md)
    inlinePatterns["image_reference"] = ImageReferencePattern(
        IMAGE_REFERENCE_RE, md
    )
    inlinePatterns["short_reference"] = ReferencePattern(
        SHORT_REF_RE, md
    )
    inlinePatterns["autolink"] = AutolinkPattern(AUTOLINK_RE, md)
    inlinePatterns["automail"] = AutomailPattern(AUTOMAIL_RE, md)
    inlinePatterns["linebreak"] = SubstituteTagPattern(LINE_BREAK_RE, 'br')
    inlinePatterns["html"] = HtmlPattern(HTML_RE, md)
    inlinePatterns["entity"] = HtmlPattern(ENTITY_RE, md)
    inlinePatterns["not_strong"] = SimpleTextPattern(NOT_STRONG_RE)
    inlinePatterns["em_strong"] = DoubleTagPattern(EM_STRONG_RE, 'strong,em')
    inlinePatterns["strong_em"] = DoubleTagPattern(STRONG_EM_RE, 'em,strong')
    inlinePatterns["strong"] = SimpleTagPattern(STRONG_RE, 'strong')
    inlinePatterns["emphasis"] = SimpleTagPattern(EMPHASIS_RE, 'em')
    inlinePatterns["strong2"] = SimpleTagPattern(SMART_STRONG_RE, 'strong')
    inlinePatterns["emphasis2"] = SimpleTagPattern(SMART_EMPHASIS_RE, 'em')
    return inlinePatterns

"""
The actual regular expressions for patterns
-----------------------------------------------------------------------------
"""

NOBRACKET = r'[^\]\[]*'
BRK = (
    r'\[(' +
    (NOBRACKET + r'(\[')*6 +
    (NOBRACKET + r'\])*')*6 +
    NOBRACKET + r')\]'
)
NOIMG = r'(?<!\!)'

# `e=f()` or ``e=f("`")``
BACKTICK_RE = r'(?<!\\)(`+)(.+?)(?<!`)\1(?!`)'

# \<
ESCAPE_RE = r'\\(.)'

# *emphasis*
EMPHASIS_RE = r'(\*)([^\*]+)\1'

# **strong**
STRONG_RE = r'(\*{2})(.+?)\1'

# __smart__strong__
SMART_STRONG_RE = r'(?<!\w)(_{2})(?!_)(.+?)(?<!_)\1(?!\w)'

# _smart_emphasis_
SMART_EMPHASIS_RE = r'(?<!\w)(_)(?!_)(.+?)(?<!_)\1(?!\w)'

# ***strongem*** or ***em*strong**
EM_STRONG_RE = r'(\*|_)\1{2}(.+?)\1(.*?)\1{2}'

# ***strong**em*
STRONG_EM_RE = r'(\*|_)\1{2}(.+?)\1{2}(.*?)\1'

# [text](url) or [text](<url>) or [text](url "title")
LINK_RE = NOIMG + BRK + \
    r'''\(\s*(<.*?>|((?:(?:\(.*?\))|[^\(\)]))*?)\s*((['"])(.*?)\11\s*)?\)'''

# ![alttxt](http://x.com/) or ![alttxt](<http://x.com/>)
IMAGE_LINK_RE = r'\!' + BRK + r'\s*\((<.*?>|([^")]+"[^"]*"|[^\)]*))\)'

# [Google][3]
REFERENCE_RE = NOIMG + BRK + r'\s?\[([^\]]*)\]'

# [Google]
SHORT_REF_RE = NOIMG + r'\[([^\]]+)\]'

# ![alt text][2]
IMAGE_REFERENCE_RE = r'\!' + BRK + '\s?\[([^\]]*)\]'

# stand-alone * or _
NOT_STRONG_RE = r'((^| )(\*|_)( |$))'

# <http://www.123.com>
AUTOLINK_RE = r'<((?:[Ff]|[Hh][Tt])[Tt][Pp][Ss]?://[^>]*)>'

# <me@example.com>
AUTOMAIL_RE = r'<([^> \!]*@[^> ]*)>'

# <...>
HTML_RE = r'(\<([a-zA-Z/][^\>]*?|\!--.*?--)\>)'

# &amp;
ENTITY_RE = r'(&[\#a-zA-Z0-9]*;)'

# two spaces at end of line
LINE_BREAK_RE = r'  \n'


def dequote(string):
    """Remove quotes from around a string."""
    if ((string.startswith('"') and string.endswith('"')) or
       (string.startswith("'") and string.endswith("'"))):
        return string[1:-1]
    else:
        return string


"""
The pattern classes
-----------------------------------------------------------------------------
"""


class Pattern(object):
    """Base class that inline patterns subclass. """

    def __init__(self, pattern, md=None):
        """
        Create an instant of an inline pattern.

        Keyword arguments:

        * pattern: A regular expression that matches a pattern

        """
        self.pattern = pattern
        self.compiled_re = re.compile(pattern, re.DOTALL | re.UNICODE)

        if md:
            self.md = md

    def getCompiledRegExp(self):
        """ Return a compiled regular expression. """
        return self.compiled_re

    def handleMatch(self, m):
        """Return a ElementTree element from the given match.

        Subclasses should override this method.

        Keyword arguments:

        * m: A re match object containing a match of the pattern.

        """
        pass  # pragma: no cover

    def type(self):
        """ Return class name, to define pattern type """
        return self.__class__.__name__

    def unescape(self, text):
        """ Processed any backslash escaped chars in string. """
        if not isinstance(text, util.text_type):
            return text
        def sub(m):
            if m.group(1) in self.md.ESCAPED_CHARS:
                return m.group(1)
            else:
                return m.group(0)
        return re.sub(ESCAPE_RE, sub, text)


class SimpleTextPattern(Pattern):
    """ Return a simple text of group(1) of a Pattern. """
    def handleMatch(self, m):
        return m.group(1)


class EscapePattern(Pattern):
    """ Return an escaped character. """

    def handleMatch(self, m):
        char = m.group(1)
        if char in self.md.ESCAPED_CHARS:
            return '%s%s%s' % (util.STX, ord(char), util.ETX)
        else:
            return None


class SimpleTagPattern(Pattern):
    """
    Return element of type `tag` with a text attribute of group(2)
    of a Pattern.

    """
    def __init__(self, pattern, tag):
        Pattern.__init__(self, pattern)
        self.tag = tag

    def handleMatch(self, m):
        el = util.etree.Element(self.tag)
        el.text = m.group(2)
        return el


class SubstituteTagPattern(SimpleTagPattern):
    """ Return an element of type `tag` with no children. """
    def handleMatch(self, m):
        return util.etree.Element(self.tag)


class BacktickPattern(Pattern):
    """ Return a `<code>` element containing the matching text. """
    def __init__(self, pattern):
        Pattern.__init__(self, pattern)
        self.tag = "code"

    def handleMatch(self, m):
        el = util.etree.Element(self.tag)
        el.text = util.AtomicString(m.group(2).strip())
        return el


class DoubleTagPattern(SimpleTagPattern):
    """Return a ElementTree element nested in tag2 nested in tag1.

    Useful for strong emphasis etc.

    """
    def handleMatch(self, m):
        tag1, tag2 = self.tag.split(",")
        el1 = util.etree.Element(tag1)
        el2 = util.etree.SubElement(el1, tag2)
        el2.text = m.group(2)
        if len(m.groups()) == 3: # TODO: confirm this is right. maybe 4?
            el2.tail = m.group(3)
        return el1


class HtmlPattern(Pattern):
    """ Store raw inline html and return a placeholder. """
    def handleMatch(self, m):
        rawhtml = m.group(1)
        place_holder = self.md.htmlStash.store(rawhtml)
        return place_holder


class LinkPattern(Pattern):
    """ Return a link element from the given match. """
    def handleMatch(self, m):
        el = util.etree.Element("a")
        el.text = m.group(1)
        title = m.group(12)
        href = m.group(8)

        if href:
            if href[0] == "<":
                href = href[1:-1]
            el.set("href", self.unescape(href.strip()))
        else:
            el.set("href", "")

        if title:
            title = self.unescape(dequote(title))
            el.set("title", title)
        return el


class ImagePattern(LinkPattern):
    """ Return a img element from the given match. """
    def handleMatch(self, m):
        el = util.etree.Element("img")
        src_parts = m.group(8).split()
        if src_parts:
            src = src_parts[0]
            if src[0] == "<" and src[-1] == ">":
                src = src[1:-1]
            el.set('src', self.unescape(src))
        else:
            el.set('src', "")
        if len(src_parts) > 1:
            el.set('title', self.unescape(dequote(" ".join(src_parts[1:]))))
        el.set('alt', self.unescape(m.group(1)))
        return el


class ReferencePattern(LinkPattern):
    """ Match to a stored reference and return link element. """

    NEWLINE_CLEANUP_RE = re.compile(r'[ ]?\n', re.MULTILINE)

    def handleMatch(self, m):
        try:
            id = m.group(8).lower()
        except IndexError:
            id = None
        if not id:
            # if we got something like "[Google][]" or "[Goggle]"
            # we'll use "google" as the id
            id = m.group(1).lower()

        # Clean up linebreaks in id
        id = self.NEWLINE_CLEANUP_RE.sub(' ', id)
        if id not in self.md.references:  # ignore undefined refs
            return None
        href, title = self.md.references[id]

        text = m.group(1)
        return self.makeTag(self.unescape(href), self.unescape(title), text)

    def makeTag(self, href, title, text):
        el = util.etree.Element('a')

        el.set('href', href)
        if title:
            el.set('title', title)

        el.text = text
        return el


class ImageReferencePattern(ReferencePattern):
    """ Match to a stored reference and return img element. """
    def makeTag(self, href, title, text):
        el = util.etree.Element("img")
        el.set("src", href)
        if title:
            el.set("title", title)
        el.set("alt", text)
        return el


class AutolinkPattern(Pattern):
    """ Return a link Element given an autolink (`<http://example/com>`). """
    def handleMatch(self, m):
        el = util.etree.Element("a")
        el.set('href', m.group(1))
        el.text = util.AtomicString(m.group(1))
        return el


class AutomailPattern(Pattern):
    """
    Return a mailto link Element given an automail link (`<foo@example.com>`).
    """
    def handleMatch(self, m):
        el = util.etree.Element('a')
        email = m.group(1)
        if email.startswith("mailto:"):
            email = email[len("mailto:"):]

        def codepoint2name(code):
            """Return entity definition by code, or the code if not defined."""
            entity = entities.codepoint2name.get(code)
            if entity:
                return "%s%s;" % (util.AMP_SUBSTITUTE, entity)
            else:
                return "%s#%d;" % (util.AMP_SUBSTITUTE, code)

        letters = [codepoint2name(ord(letter)) for letter in email]
        el.text = util.AtomicString(''.join(letters))

        mailto = "mailto:" + email
        mailto = "".join([util.AMP_SUBSTITUTE + '#%d;' %
                          ord(letter) for letter in mailto])
        el.set('href', mailto)
        return el
