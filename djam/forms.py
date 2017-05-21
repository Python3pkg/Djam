# -*- coding: utf-8 -*-
"""
    djam.forms
    ~~~~~~~~~~

    Improve (slightly) django Form to ease working with objects that are not
    django models...

    :email: devel@amvtek.com
"""


from copy import copy
from collections import Iterable

from django import forms
from django.conf import settings
import collections

class AddErrorMixin:
    """
    Form mixin that eases performing additional validation out of the form
    When you need to pass additional state to Form or Field to perform
    validation, this can be helpfull
    """

    def set_error(self, fieldname, *msgs):
        # add msgs to form errors...
        msglist = self.errors.setdefault(fieldname, [])
        msglist.extend(msgs)

        # django doc recommends to remove invalid field value from cleaned_data
        cleaned_data = getattr(self, 'cleaned_data', None)
        if cleaned_data is not None:
            cleaned_data.pop(fieldname, None)


class ObjForm(forms.Form, AddErrorMixin):
    """
    base Form that make it easier to work with non ORM object...
    ---
    api is inspired by WTForm package
    """

    def get_initial_object(self, kwargs):
        """remove and return kwargs['initial'] if it is not a dict..."""

        if 'initial' in kwargs:

            # check if initial can be accessed as a dict
            initial = kwargs['initial']
            isObj = False
            for method in ['keys', '__getitem__']:
                if not isinstance(getattr(initial, method, None), collections.Callable):
                    isObj = True
                    break

            if isObj:
                return kwargs.pop('initial')

    def __init__(self, *args, **kwargs):

        # may pull initial values out of obj or data to validate from dataObj
        dictData = {}
        initialObj = kwargs.pop('obj', None) or self.get_initial_object(kwargs)
        dataObj = kwargs.pop("dataObj", None)

        obj = initialObj or dataObj

        if obj:
            for field in list(self.base_fields.keys()):
                value = getattr(obj, field, None)
                if value is not None:
                    dictData[field] = value

        # initialize django form...
        if initialObj is not None and kwargs.get('initial', None) is None:
            if dictData:
                kwargs['initial'] = dictData

        # provide data for validation
        if dataObj is not None and kwargs.get('data', None) is None:
            if dictData:
                kwargs['data'] = dictData

        super(ObjForm, self).__init__(*args, **kwargs)

    def populate_obj(self, obj, *attrs):
        "transfer form cleaned_datas in obj..."

        cleaned_data = self.cleaned_data  # local alias
        attrs = attrs or list(cleaned_data.keys())

        for aname in attrs:
            setattr(obj, aname, cleaned_data.get(aname))

        return obj


def fieldset_factory(fieldsets, prefix_init=None):
    """
    returns a Form class that proxies a sequence of Fieldset.
    Each Fieldset is defined by an html prefix and a Form class...
    """

    # validate fieldsets
    names = set([])
    for name, formClass in fieldsets:
        if name in names:
            raise ValueError("Multiple use of %s prefix" % name)
        if not isinstance(formClass, collections.Callable):
            raise ValueError("Invalid Form class %s" % name)
        if not isinstance(getattr(formClass, 'is_valid', None), collections.Callable):
            raise ValueError("Invalid Form class %s" % name)
        names.add(name)

    if isinstance(prefix_init, collections.Callable):
        prefix_init = staticmethod(prefix_init)

    class FSForm(dict):

        _fieldsets = dict(fieldsets)
        _prefix_init = prefix_init
        __isValid = None

        def __init__(self, *args, **kwargs):

            prefix_init = kwargs.pop('prefix_init', False) or self._prefix_init

            if prefix_init:

                initial = kwargs.pop('initial', None)
                obj = kwargs.pop('obj', None)
                if isinstance(prefix_init, collections.Callable):
                    # use prefix_init to finish initialization...
                    initial = initial and prefix_init(initial)
                    obj = obj and prefix_init(obj)

                for pfx, Form in list(self._fieldsets.items()):
                    kw = copy(kwargs)
                    if initial:
                        kw['initial'] = initial.get(pfx)
                    if obj:
                        kw['obj'] = obj.get(pfx)
                    kw['prefix'] = pfx
                    self[pfx] = Form(*args, **kw)
            else:
                for pfx, Form in list(self._fieldsets.items()):
                    kw = copy(kwargs)
                    kw['prefix'] = pfx
                    self[pfx] = Form(*args, **kw)

        def is_valid(self):
            "call is_valid on each of the internal 'fieldset' form..."

            if self.__isValid is None:
                isValid = True
                for pfx, form in list(self.items()):
                    if pfx in self._fieldsets:
                        isValid &= form.is_valid()
                self.__isValid = isValid
            return self.__isValid

        def populate_obj(self, obj, *attrs):
            "call populate_obj on each of the internal 'fieldset' form..."

            fs = self._fieldsets  # local alias
            for pfx, form in list(self.items()):
                if pfx in fs:
                    if isinstance(getattr(form, 'populate_obj', None), collections.Callable):
                        form.populate_obj(obj, *attrs)
                    elif isinstance(form, Iterable):
                        # we may have a formset, will attend iterating it...
                        for f in form:
                            if isinstance(getattr(f, 'populate_obj', None), collections.Callable):
                                f.populate_obj(obj, *attrs)

        def __repr__(self):
            return "<FiedSetForm%s>" % str(tuple(self._fieldsets.keys()))

    return FSForm
