from calendar import month_name
from collections import defaultdict

from django.http import Http404
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import get_object_or_404
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from django import VERSION
from django.utils.translation import ugettext as _

from mezzanine_wiki.models import WikiPage, WikiCategory
#from mezzanine.blog.feeds import PostsRSS, PostsAtom
from mezzanine.conf import settings
from mezzanine.generic.models import AssignedKeyword, Keyword
from mezzanine.utils.views import render, paginate
from mezzanine_wiki.forms import WikiPageForm


def wiki_index(request, template_name='mezawiki/wiki_page_detail.html'):
    """
    Redirects to the default wiki index name.
    """
    return HttpResponseRedirect(
        reverse('wiki_page_detail', args=[settings.WIKI_DEFAULT_INDEX])
    )


def wiki_page_list(request, tag=None, username=None,
                   category=None, template="mezawiki/wiki_page_list.html"):
    """
    Display a list of wiki pages that are filtered by tag, 
    author or category.

    Custom templates are checked for using the name
    ``mezawiki/wiki_page_list_XXX.html`` where ``XXX`` is either the
    category slug or author's username if given.
    """
    settings.use_editable()
    templates = []
    wiki_pages = WikiPage.objects.published(for_user=request.user)
    if tag is not None:
        tag = get_object_or_404(Keyword, slug=tag)
        wiki_pages = wiki_pages.filter(keywords__in=tag.assignments.all())
    if category is not None:
        category = get_object_or_404(WikiCategory, slug=category)
        wiki_pages = wiki_pages.filter(categories=category)
        templates.append(u"mezawiki/wiki_post_list_%s.html" %
                          unicode(category.slug))
    author = None
    if username is not None:
        author = get_object_or_404(User, username=username)
        wiki_pages = wiki_pages.filter(user=author)
        templates.append(u"mezawiki/wiki_page_list_%s.html" % username)

    # We want to iterate keywords and categories for each wiki page
    # without triggering "num posts x 2" queries.
    #
    # For Django 1.3 we create dicts mapping wiki page IDs to lists of
    # categories and keywords, and assign these to each wiki page
    #
    # For Django 1.4 we just use prefetch related.

    if VERSION >= (1, 4):
        rel = ("categories", "keywords__keyword")
        wiki_pages = wiki_pages.select_related("user").prefetch_related(*rel)
    else:
        wiki_pages = list(wiki_pages.select_related("user"))
        categories = defaultdict(list)
        if wiki_pages:
            ids = ",".join([str(p.id) for p in wiki_pages])
            for cat in WikiCategory.objects.raw(
                "SELECT * FROM mezawiki_wikicategory "
                "JOIN mezawiki_wikipage_categories "
                "ON mezawiki_wikicategory.id = wikicategory_id "
                "WHERE wikipage_id IN (%s)" % ids):
                categories[cat.wikipage_id].append(cat)
        keywords = defaultdict(list)
        wikipage_type = ContentType.objects.get(app_label="mezawiki",
                                                model="wikipage")
        assigned = AssignedKeyword.objects.filter(wikipage__in=wiki_pages,
                        content_type=wikipage_type).select_related("keyword")
        for a in assigned:
            keywords[a.object_pk].append(a.keyword)
    for i, page in enumerate(wiki_pages):
        if VERSION < (1, 4):
            setattr(wiki_pages[i], "category_list", categories[page.id])
            setattr(wiki_pages[i], "keyword_list", keywords[page.id])
        else:
            setattr(wiki_pages[i], "category_list",
                    page.categories.all())
            setattr(wiki_pages[i], "keyword_list",
                    [k.keyword for k in page.keywords.all()])

    wiki_pages = paginate(wiki_pages,
                          request.GET.get("page", 1),
                          settings.WIKI_PAGES_PER_PAGE,
                          settings.MAX_PAGING_LINKS)
    context = {"wiki_pages": wiki_pages,
               "tag": tag, "category": category, "author": author}
    templates.append(template)
    return render(request, templates, context)


def wiki_page_detail(request, slug, year=None, month=None,
                     template="mezawiki/wiki_page_detail.html"):
    """
    Displays a wiki page.
    Redirects to the edit view if the page doesn't exist.

    Custom templates are checked for using the name
    ``mezawiki/wiki_page_detail_XXX.html``
    where ``XXX`` is the wiki pages's slug.
    """
    try:
        wiki_pages = WikiPage.objects.published(for_user=request.user)
        wiki_page = wiki_pages.get(slug=slug)
    except WikiPage.DoesNotExist:
        return HttpResponseRedirect(reverse('wiki_page_edit', args=[slug]))
    context = {"wiki_page": wiki_page}
    templates = [u"mezawiki/wiki_page_detail_%s.html" % unicode(slug), template]
    return render(request, templates, context)


@login_required
def wiki_page_edit(request, slug, 
                     template="mezawiki/wiki_page_edit.html"):
    """
    Displays the form for editing and deleting a page.

    Custom templates are checked for using the name
    ``mezawiki/wiki_page_edit_XXX.html``
    where ``XXX`` is the wiki pages's slug.
    """
    try:
        wiki_pages = WikiPage.objects.published(for_user=request.user)
        wiki_page = wiki_pages.get(slug=slug)
        initial = {}
    except WikiPage.DoesNotExist:
        wiki_page = WikiPage(slug=slug)
        wiki_page.is_initial = True
        initial = {'content': _('Describe your new page %s here...' % slug)}
                   #'message': _('Initial revision')}

    if request.method == 'POST':
        form = WikiPageForm(request.POST, instance=wiki_page)
        if form.is_valid():
            page = form.save(commit=False)
            page.user = request.user
            page.title = slug
            page.save()
            return HttpResponseRedirect(
                reverse('wiki_page_detail', args=[slug]))
    else:
        form = WikiPageForm(initial=initial, instance=wiki_page)

    context = {"wiki_page": wiki_page, 'form': form}
    templates = [u"mezawiki/wiki_page_edit_%s.html" % unicode(slug), template]
    return render(request, templates, context)


