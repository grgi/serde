"""
This module contains Field classes for `Models <serde.model.Model>`.

Fields handle serializing, deserializing, and validation of input values for
Model objects. They are instantiated when assigned to the Model. Fields
support extra serialization, deserialization, and validation of values without
having to subclass `Field`.

Note: Extra serializers are called prior to the default field serialization,
while extra deserializers, and validators are called after the default
operations.

::

    >>> def assert_is_odd(value):
    ...     assert value % 2 != 0, 'value is not odd!'

    >>> class Person(Model):
    ...     name = Str(deserializers=[lambda s: s.strip()])
    ...     fave_number = Optional(Int, validators=[assert_is_odd])
    ...     fave_color = Optional(Choice(['black', 'pink']), default='pink')

    >>> person = Person('William Shakespeare', fave_number=455)
    >>> person.name
    'William Shakespeare'
    >>> person.fave_number
    455
    >>> person.fave_color
    'pink'

    >>> Person.from_dict({'name': 'Beyonce', 'fave_number': 4})
    Traceback (most recent call last):
    ...
    serde.exceptions.ValidationError: value is not odd!

The `create()` method can be used to generate a new Field class from arbitrary
functions without having to manually subclass a Field. For example if we wanted
a `Percent` field we would do the following.

::

    >>> Percent = fields.create(
    ...     'Percent',
    ...     Float,
    ...     validators=[validate.between(0.0, 100.0)]
    ... )

    >>> issubclass(Percent, Float)
    True

Here is an example where we subclass a field and override the serialize,
deserialize, and validate methods. Note: there is already an Email field in this
module, this is just an example of how it could be created.

::

    >>> class Email(Field):
    ...
    ...     def serialize(self, value):
    ...         return value.strip()
    ...
    ...     def deserialize(self, value):
    ...         return value.strip()
    ...
    ...     def validate(self, value):
    ...         assert isinstance(value, str)
    ...         validate.email(value)

    >>> class User(Model):
    ...     email = Email()

    >>> user = User(email='john@smith.com')
    >>> user.email
    'john@smith.com'

    >>> user.to_dict()
    OrderedDict([('email', 'john@smith.com')])

"""

import datetime
import uuid

import isodate

from serde import validate
from serde.exceptions import SerdeError, SkipSerialization, ValidationError
from serde.utils import zip_equal


__all__ = [
    'Bool',
    'Boolean',
    'Bytes',
    'Choice',
    'Complex',
    'Date',
    'DateTime',
    'Dict',
    'Dictionary',
    'Domain',
    'Email',
    'Field',
    'Float',
    'Instance',
    'Int',
    'Integer',
    'IpAddress',
    'Ipv4Address',
    'Ipv6Address',
    'List',
    'MacAddress',
    'Nested',
    'Optional',
    'Slug',
    'Str',
    'String',
    'Time',
    'Tuple',
    'Url',
    'Uuid',
    'create'
]


def _resolve_to_field_instance(thing, none_allowed=True):
    """
    Resolve an arbitrary object to a `Field` instance.

    Args:
        thing: anything to resolve to a Field instance.
        none_allowed (bool): if set then a thing of None will be resolved to a
            generic Field.

    Returns:
        Field: a field instance.
    """
    # We import Model here to avoid circular dependency problems.
    from serde.model import Model

    # If the thing is None then return a generic Field instance.
    if none_allowed and thing is None:
        return Field()

    # If the thing is a Field instance then thats great.
    elif isinstance(thing, Field):
        return thing

    # If the thing is a subclass of Field then attempt to create an instance.
    # This could fail the Field expects positional arguments.
    try:
        if issubclass(thing, Field):
            return thing()
    except TypeError:
        pass

    # If the thing is a subclass of Model then create a Nested instance.
    try:
        if issubclass(thing, Model):
            return Nested(thing)
    except TypeError:
        pass

    # If the thing is a built-in type that we support then create an Instance
    # with that type.
    field_class = {
        bool: Bool,
        bytes: Bytes,
        complex: Complex,
        dict: Dict,
        float: Float,
        int: Int,
        list: List,
        str: Str,
        tuple: Tuple
    }.get(thing, None)

    if field_class is not None:
        return field_class()

    raise TypeError(
        '{!r} is not a Field, a Model class, an instance of a Field, or a supported type'
        .format(thing)
    )


class Field(object):
    """
    A field on a `~serde.model.Model`.

    Fields handle serializing, deserializing, and validation of
    input values for Model objects.
    """

    # This is so we can get the order the fields were instantiated in.
    __counter = 0

    def __init__(self, rename=None, serializers=None, deserializers=None, validators=None):
        """
        Create a new Field.

        Args:
            rename (str): override the name for the field when serializing and
                expect this name when deserializing.
            serializers (list): a list of serializer functions taking the value
                to serialize as an argument. The functions need to raise an
                `Exception` if they fail. These serializer functions will be
                applied before the primary serializer on this Field.
            deserializers (list): a list of deserializer functions taking the
                value to deserialize as an argument. The functions need to raise
                an `Exception` if they fail. These deserializer functions will
                be applied after the primary deserializer on this Field.
            validators (list): a list of validator functions taking the value
                to validate as an argument. The functions need to raise an
                `Exception` if they fail.
        """
        super(Field, self).__init__()

        self.id = Field.__counter
        Field.__counter += 1

        self.rename = rename
        self.serializers = serializers or []
        self.deserializers = deserializers or []
        self.validators = validators or []

    def _attrs(self):
        """
        Return all attributes of this Field except "id" and "_name".
        """
        return {
            name: value for name, value in vars(self).items()
            if name not in ('id', '_name')
        }

    def __eq__(self, other):
        """
        Whether two Fields are the same.
        """
        return isinstance(other, self.__class__) and self._attrs() == other._attrs()

    def __setattr__(self, name, value):
        """
        Set a named attribute on a Field.

        Raises:
            `~serde.exceptions.SerdeError`: when the _name attribute is set
                after it has already been set.
        """
        if name == '_name' and hasattr(self, '_name'):
            raise SerdeError('Field instance used multiple times')

        super(Field, self).__setattr__(name, value)

    def _serialize(self, value):
        """
        Serialize the given value according to this Field's specification.

        This method is called by the Model.

        Args:
            value: the value to serialize.

        Returns:
            the serialized value.
        """
        for serializer in self.serializers:
            value = serializer(value)

        value = self.serialize(value)

        return value

    def _deserialize(self, value):
        """
        Deserialize the given value according to this Field's specification.

        This method is called by the Model.

        Args:
            value: the value to deserialize.

        Returns:
            the deserialized value.
        """
        value = self.deserialize(value)

        for deserializer in self.deserializers:
            value = deserializer(value)

        return value

    def _normalize(self, value):
        """
        Normalize the given value according to this Field's specification.

        This is called after deserialization and on initialization, both before
        validation.

        Args:
            value: the value to normalize.

        Returns:
            the normalized value.
        """
        return value

    def _validate(self, value):
        """
        Validate the given value according to this Field's specification.

        This method is called by the Model.

        Args:
            value: the value to validate.
        """
        self.validate(value)

        for validator in self.validators:
            validator(value)

    @property
    def name(self):
        """
        The name of this Field.

        This is the rename value, given when the Field is instantiated,
        otherwise it is the attribute name of this Field on the Model.
        """
        try:
            name = self._name
        except AttributeError:
            raise SerdeError('Field is not on a Model')

        if self.rename is not None:
            return self.rename

        return name

    def serialize(self, value):
        """
        Serialize the given value according to this Field's specification.

        Args:
            value: the value to serialize.

        Returns:
            the serialized value.
        """
        return value

    def deserialize(self, value):
        """
        Deserialize the given value according to this Field's specification.

        Args:
            value: the value to deserialize.

        Returns:
            the deserialized value.
        """
        return value

    def validate(self, value):
        """
        Validate the given value according to this Field's specification.

        Args:
            value: the value to validate.
        """
        if value is None:
            raise ValidationError('None is not a valid Field value')


def _create_serialize(cls, serializers):
    """
    Create a new serialize method with extra serializer functions.
    """
    def serialize(self, value):
        for serializer in serializers:
            value = serializer(value)
        value = super(cls, self).serialize(value)
        return value

    serialize.__doc__ = serializers[0].__doc__

    return serialize


def _create_deserialize(cls, deserializers):
    """
    Create a new deserialize method with extra deserializer functions.
    """
    def deserialize(self, value):
        value = super(cls, self).deserialize(value)
        for deserializer in deserializers:
            value = deserializer(value)
        return value

    deserialize.__doc__ = deserializers[0].__doc__

    return deserialize


def _create_validate(cls, validators):
    """
    Create a new validate method with extra validator functions.
    """
    def validate(self, value):
        super(cls, self).validate(value)
        for validator in validators:
            validator(value)

    validate.__doc__ = validators[0].__doc__

    return validate


def create(name, base=None, args=None, serializers=None, deserializers=None, validators=None):
    """
    Create a new Field class.

    This is a convenience method for creating new Field classes from arbitrary
    serializer, deserializer, and/or validator functions.

    Args:
        name (str): the name of the class.
        base (Field): the base Field class to subclass.
        args (tuple): positional arguments for the base class __init__ method.
        serializers (list): a list of serializer functions taking the value to
            serialize as an argument. The functions need to raise an `Exception`
            if they fail. These serializer functions will be applied before the
            primary serializer on this Field.
        deserializers (list): a list of deserializer functions taking the value
            to deserialize as an argument. The functions need to raise an
            `Exception` if they fail. These deserializer functions will be
            applied after the primary deserializer on this Field.
        validators (list): a list of validator functions taking the value to
            validate as an argument. The functions need to raise an `Exception`
            if they fail.

    Returns:
        class: a new Field class.
    """
    if not base:
        base = Field

    cls = type(name, (base,), {})

    if args:
        def __init__(self, **kwargs):  # noqa: N807
            super(cls, self).__init__(*args, **kwargs)

        __init__.__doc__ = (
            'Create a new {}.\n\n'
            'Args:\n'
            '    **kwargs: keyword arguments for the `{}` constructor.'
        ).format(name, base.__name__)
        setattr(cls, '__init__', __init__)

    if serializers:
        setattr(cls, 'serialize', _create_serialize(cls, serializers))

    if deserializers:
        setattr(cls, 'deserialize', _create_deserialize(cls, deserializers))

    if validators:
        setattr(cls, 'validate', _create_validate(cls, validators))

    return cls


class Instance(Field):
    """
    A `Field` that is an instance of the given type.
    """

    def __init__(self, type, **kwargs):
        """
        Create a new Instance.

        Args:
            type: the type that this Field wraps.
            **kwargs: keyword arguments for the `Field` constructor.
        """
        super(Instance, self).__init__(**kwargs)
        self.type = type

    def validate(self, value):
        """
        Validate the given value is an instance of the specified type.

        Args:
            value: the value to validate.
        """
        super(Instance, self).validate(value)
        validate.instance(self.type)(value)


class Nested(Instance):
    """
    A `Field` for `~serde.model.Model` fields.

    This is wrapper Field for Models to support sub-Models. The serialize and
    deserialize methods call the `~serde.model.Model.to_dict()` and
    `~serde.model.Model.from_dict()`  methods on the Model class. This allows
    complex nested Models.

    ::

        >>> class Birthday(Model):
        ...     day = Int(validators=[validate.between(1, 31)])
        ...     month = Str()

        >>> class Person(Model):
        ...     name = Str()
        ...     birthday = Nested(Birthday)

        >>> person = Person('Beyonce', birthday=Birthday(4, 'September'))
        >>> person.name
        'Beyonce'
        >>> person.birthday.day
        4
        >>> person.birthday.month
        'September'

        >>> assert person.to_dict() == {
        ...     'name': 'Beyonce',
        ...     'birthday': {
        ...         'day': 4,
        ...         'month': 'September'
        ...     }
        ... }

        >>> person = Person.from_dict({
        ...     'name': 'Beyonce',
        ...     'birthday': {
        ...         'day': 4,
        ...         'month': 'September'
        ...     }
        ... })
        >>> person.name
        'Beyonce'
        >>> person.birthday.day
        4
        >>> person.birthday.month
        'September'
    """

    def __init__(self, model, dict=None, strict=True, **kwargs):
        """
        Create a new Nested.

        Args:
            model: the Model class that this Nested wraps.
            dict (type): the class of the deserialized dictionary. This defaults
                to an `~collections.OrderedDict` so that the fields will be
                returned in the order they were defined on the Model.
            strict (bool): if set to False then no exception will be raised when
                unknown dictionary keys are present when deserializing.
            **kwargs: keyword arguments for the `Field` constructor.
        """
        super(Nested, self).__init__(model, **kwargs)
        self.dict = dict
        self.strict = strict

    def serialize(self, value):
        """
        Serialize the given `Model` instance as a dictionary.

        Args:
            value (Model): the model to serialize.

        Returns:
            dict: the serialized dictionary.
        """
        value = value.to_dict(dict=self.dict)
        return super(Nested, self).serialize(value)

    def deserialize(self, value):
        """
        Deserialize the given dictionary to a `Model` instance.

        Args:
            value (dict): the dictionary to deserialize.

        Returns:
            Model: the deserialized model.
        """
        value = self.type.from_dict(value, strict=self.strict)
        return super(Nested, self).deserialize(value)


class Optional(Field):
    """
    An optional Field.

    An Optional is a Field that is allowed to be None. Serialization,
    deserialization, and validation using the wrapped Field will only be called
    if the value is not None. The wrapped Field can be specified using a Field
    class, a Field instance, a Model class, or a built-in type that has a
    corresponding Field type in this library.

    ::

        >>> class Quote(Model):
        ...     author = Optional(Str)
        ...     year = Optional(Int, default=2004)
        ...     content = Str()

        >>> quote = Quote(year=2000, content='Beautiful is better than ugly.')
        >>> assert quote.author is None
        >>> quote.year
        2000
        >>> quote.content
        'Beautiful is better than ugly.'

        >>> assert quote.to_dict() == {
        ...     'content': 'Beautiful is better than ugly.',
        ...     'year': 2000
        ... }

        >>> quote = Quote.from_dict({
        ...     'author': 'Tim Peters',
        ...     'content': 'Now is better than never',
        ... })
        >>> quote.author
        'Tim Peters'
        >>> quote.year
        2004
        >>> quote.content
        'Now is better than never'
    """

    def __init__(self, inner=None, default=None, **kwargs):
        """
        Create a new Optional.

        Args:
            inner: the the Field class/instance that this Optional wraps.
            default: a value to use if there is no input field value or the
                input value is None. This can also be a callable that generates
                the default. The function must take no arguments.
            **kwargs: keyword arguments for the `Field` constructor.
        """
        super(Optional, self).__init__(**kwargs)
        self.inner = _resolve_to_field_instance(inner)
        self.default = default

    def _normalize(self, value):
        """
        Normalize the given value according to the inner Field's specification.

        This is called after deserialization and on initialization, both before
        validation. If a default is defined, this method will set the value to
        the default if the value is None.

        Args:
            value: the value to normalize.

        Returns:
            the normalized value.
        """
        if value is None and self.default is not None:
            if callable(self.default):
                value = self.default()
            else:
                value = self.default

        return value

    def serialize(self, value):
        """
        Serialize the given value according to the inner Field's specification.

        Serialization will only be called if the value is not None.

        Args:
            value: the value to serialize.

        Returns:
            the serialized value.
        """
        if value is None:
            raise SkipSerialization()

        return self.inner.serialize(value)

    def deserialize(self, value):
        """
        Deserialize the given value according to the inner Field's specification.

        Deserialization will only be called if the value is not None.

        Args:
            value: the value to deserialize.

        Returns:
            the deserialized value or None.
        """
        if value is not None:
            return self.inner.deserialize(value)

    def validate(self, value):
        """
        Validate the given value according to the inner Field's specification.

        Validation will only be called if the value is not None.

        Args:
            value: the value to validate.
        """
        if value is not None:
            self.inner.validate(value)


class Dict(Instance):
    """
    A dictionary Field with a required key and value type.

    This field represents the built-in `dict` type. Each key and value will be
    serialized, deserialized, and validated with the specified key and value
    types. The key and value types can be specified using Field classes, Field
    instances, Model classes, or built-in types that have a corresponding Field
    type in this library.

    Consider an example model with a constants attribute which is map of strings
    to floats.

    ::

        >>> class Example(Model):
        ...     constants = Dict(str, float)

        >>> example = Example({'pi': 3.1415927, 'e': 2.7182818})
        >>> example.constants['pi']
        3.1415927
        >>> example.constants['e']
        2.7182818

        >>> d = example.to_dict()
        >>> d['constants']['pi']
        3.1415927
        >>> d['constants']['e']
        2.7182818

        >>> Example({'pi': '3.1415927'})
        Traceback (most recent call last):
            ...
        serde.exceptions.ValidationError: expected 'float' but got 'str'

        >>> Example.from_dict({'constants': {100: 3.1415927}})
        Traceback (most recent call last):
            ...
        serde.exceptions.ValidationError: expected 'str' but got 'int'
    """

    def __init__(self, key=None, value=None, **kwargs):
        """
        Create a new Dict.

        Args:
            key (Field): the Field class/instance for keys in this Dict.
            value (Field): the Field class/instance for values in this Dict.
            **kwargs: keyword arguments for the `Field` constructor.
        """
        super(Dict, self).__init__(dict, **kwargs)
        self.key = _resolve_to_field_instance(key)
        self.value = _resolve_to_field_instance(value)

    def serialize(self, value):
        """
        Serialize the given dictionary.

        Each key and value in the dictionary will be serialized with the
        specified key and value Field instances.

        Args:
            value (dict): the dictionary to serialize.

        Returns:
            dict: the serialized dictionary.
        """
        value = {self.key.serialize(k): self.value.serialize(v) for k, v in value.items()}
        return super(Dict, self).serialize(value)

    def deserialize(self, value):
        """
        Deserialize the given dictionary.

        Each key and value in the dictionary will be deserialized with the
        specified key and value Field instances.

        Args:
            value (dict): the dictonary to deserialize.

        Returns:
            dict: the deserialized dictionary.
        """
        value = super(Dict, self).deserialize(value)
        return {self.key.deserialize(k): self.value.deserialize(v) for k, v in value.items()}

    def validate(self, value):
        """
        Validate the given dictionary.

        Each key and value in the dictionary will be validated with the
        specified key and value Field instances.

        Args:
            value (dict): the dictionary to validate.
        """
        super(Dict, self).validate(value)

        for k, v in value.items():
            self.key.validate(k)
            self.value.validate(v)


class List(Instance):
    """
    A list Field with a required element type.

    This field represents the built-in `list` type. Each element will be
    serialized, deserialized, and validated with the specified element type. The
    element type can be specified using Field classes, Field instances, Model
    classes, or built-in types that have a corresponding Field type in this
    library.

    Consider a user model that can have multiple emails

    ::

        >>> class User(Model):
        ...     emails = List(str)

        >>> user = User(['john@smith.com', 'john.smith@email.com'])
        >>> user.emails[0]
        'john@smith.com'
        >>> user.emails[1]
        'john.smith@email.com'

        >>> User(emails={'john@smith.com': None })
        Traceback (most recent call last):
            ...
        serde.exceptions.ValidationError: expected 'list' but got 'dict'

        >>> User.from_dict({'emails': [1234]})
        Traceback (most recent call last):
            ...
        serde.exceptions.ValidationError: expected 'str' but got 'int'
    """

    def __init__(self, element=None, **kwargs):
        """
        Create a new List.

        Args:
            element (Field): the Field class/instance for elements in the List.
            **kwargs: keyword arguments for the `Field` constructor.
        """
        super(List, self).__init__(list, **kwargs)
        self.element = _resolve_to_field_instance(element)

    def serialize(self, value):
        """
        Serialize the given list.

        Each element in the list will be serialized with the specified element
        Field instance.

        Args:
            value (list): the list to serialize.

        Returns:
            list: the serialized list.
        """
        value = [self.element.serialize(v) for v in value]
        return super(List, self).serialize(value)

    def deserialize(self, value):
        """
        Deserialize the given list.

        Each element in the list will be deserialized with the specified element
        Field instance.

        Args:
            value (list): the list to deserialize.

        Returns:
            list: the deserialized list.
        """
        value = super(List, self).deserialize(value)
        return [self.element.deserialize(v) for v in value]

    def validate(self, value):
        """
        Validate the given list.

        Each element in the list will be validated with the specified element
        Field instance.

        Args:
            value (list): the list to validate.
        """
        super(List, self).validate(value)

        for v in value:
            self.element.validate(v)


class Tuple(Instance):
    """
    A tuple Field with required element types.

    Each element will be serialized, deserialized, and validated with the
    specified element type. The given element types can be specified using Field
    classes, Field instances, Model classes, or built-in types that have a
    corresponding Field type in this library.

    Consider an example person that has a name and a birthday

    ::

        >>> class Person(Model):
        ...     name = Str()
        ...     birthday = Tuple(int, str, int)

        >>> person = Person('Ross MacArthur', (19, 'June', 1994))
        >>> person.name
        'Ross MacArthur'
        >>> person.birthday[0]
        19
        >>> person.birthday[1]
        'June'
        >>> person.birthday[2]
        1994

        >>> Person('Beyonce', birthday=(4, 'September'))
        Traceback (most recent call last):
            ...
        serde.exceptions.ValidationError: iterables have different lengths

        >>> Person.from_dict({'name': 'Beyonce', 'birthday': (4, 9, 1994)})
        Traceback (most recent call last):
            ...
        serde.exceptions.ValidationError: expected 'str' but got 'int'
    """

    def __init__(self, *elements, **kwargs):
        """
        Create a new Tuple.

        Args:
            *elements (Field): the Field classes/instances for elements in this
                Tuple.
            **kwargs: keyword arguments for the `Field` constructor.
        """
        super(Tuple, self).__init__(tuple, **kwargs)
        self.elements = tuple(_resolve_to_field_instance(e, none_allowed=False) for e in elements)

    def serialize(self, value):
        """
        Serialize the given tuple.

        Each element in the tuple will be serialized with the specified element
        Field instance.

        Args:
            value (tuple): the tuple to serialize.

        Returns:
            tuple: the serialized tuple.
        """
        return tuple(e.serialize(v) for e, v in zip_equal(self.elements, value))

    def deserialize(self, value):
        """
        Deserialize the given tuple.

        Each element in the tuple will be deserialized with the specified
        element Field instance.

        Args:
            value (tuple): the tuple to deserialize.

        Returns:
            tuple: the deserialized tuple.
        """
        value = super(Tuple, self).deserialize(value)
        return tuple(e.deserialize(v) for e, v in zip_equal(self.elements, value))

    def validate(self, value):
        """
        Validate the given tuple.

        Each element in the tuple will be validated with the specified element
        Field instance.

        Args:
            value (tuple): the tuple to validate.
        """
        super(Tuple, self).validate(value)

        for e, v in zip_equal(self.elements, value):
            e.validate(v)


#: This field represents the built-in `bool` type.
Bool = create('Bool', base=Instance, args=(bool,))

#: This field represents the built-in `complex` type.
Complex = create('Complex', base=Instance, args=(complex,))

#: This field represents the built-in `float` type.
Float = create('Float', base=Instance, args=(float,))

#: This field represents the built-in `int` type.
Int = create('Int', base=Instance, args=(int,))

#: This field represents the built-in `str` type.
Str = create('Str', base=Instance, args=(str,))

#: This field represents the built-in `bytes` type.
Bytes = create('Bytes', base=Instance, args=(bytes,)) if bytes != str else Str

try:
    #: This field represents the built-in `basestring` type.
    BaseString = create('BaseString', base=Instance, args=(basestring,))
except NameError:
    pass

try:
    #: This field represents the built-in `unicode` type.
    Unicode = create('Unicode', base=Instance, args=(unicode,))
except NameError:
    pass

# Str types with extra validation.
Domain = create('Domain', base=Str, validators=[validate.domain])
Email = create('Email', base=Str, validators=[validate.email])
IpAddress = create('IpAddress', base=Str, validators=[validate.ip_address])
Ipv4Address = create('Ipv4Address', base=Str, validators=[validate.ipv4_address])
Ipv6Address = create('Ipv6Address', base=Str, validators=[validate.ipv6_address])
MacAddress = create('MacAddress', base=Str, validators=[validate.mac_address])
Slug = create('Slug', base=Str, validators=[validate.slug])
Url = create('Url', base=Str, validators=[validate.url])

# Aliases
Boolean = Bool
Dictionary = Dict
Integer = Int
String = Str


class Choice(Field):
    """
    One of a given selection of values.

    This field checks if the input data is one of the allowed values. These
    values do not need to be the same type.

    ::

        >>> class Car(Model):
        ...     color = Choice(['black', 'blue', 'red'])

        >>> car = Car.from_dict({'color': 'blue'})
        >>> car.color
        'blue'
        >>> car.to_dict()
        OrderedDict([('color', 'blue')])
        >>> Car('yellow')
        Traceback (most recent call last):
        ...
        serde.exceptions.ValidationError: 'yellow' is not a valid choice
    """

    def __init__(self, choices, **kwargs):
        """
        Create a new Choice.

        Args:
            choices: a list/range/tuple of allowed values.
            **kwargs: keyword arguments for the `Field` constructor.
        """
        super(Choice, self).__init__(**kwargs)
        self.choices = choices

    def validate(self, value):
        """
        Validate that the given value is one of the choices.

        Args:
            value: the value to validate.
        """
        super(Choice, self).validate(value)
        validate.contains(self.choices)(value)


class DateTime(Instance):
    """
    A `~datetime.datetime` field.

    This field serializes `~datetime.datetime` objects as strings and
    deserializes string representations of datetimes as `~datetime.datetime`
    objects.

    The date format can be specified. It will default to ISO 8601.

    ::

        >>> class Entry(Model):
        ...     timestamp = DateTime(format='%Y-%m-%d %H:%M:%S')

        >>> entry = Entry(datetime.datetime(2001, 9, 11, 12, 5, 48))
        >>> entry.to_dict()
        OrderedDict([('timestamp', '2001-09-11 12:05:48')])
    """

    type = datetime.datetime

    def __init__(self, format='iso8601', **kwargs):
        """
        Create a new DateTime.

        Args:
            format (str): the datetime format to use. "iso8601" may be used for
                ISO 8601 datetimes.
            **kwargs: keyword arguments for the `Field` constructor.
        """
        super(DateTime, self).__init__(self.__class__.type, **kwargs)
        self.format = format

    def serialize(self, value):
        """
        Serialize the given `~datetime.datetime` as a string.

        Args:
            value (~datetime.datetime): the datetime object to serialize.

        Returns:
            str: a string representation of the datetime.
        """
        if self.format == 'iso8601':
            return value.isoformat()
        else:
            return value.strftime(self.format)

    def deserialize(self, value):
        """
        Deserialize the given string as a `~datetime.datetime`.

        Args:
            value (str): the string to deserialize.

        Returns:
            ~datetime.datetime: the deserialized datetime.
        """
        if self.format == 'iso8601':
            return isodate.parse_datetime(value)
        else:
            return datetime.datetime.strptime(value, self.format)


class Date(DateTime):
    """
    A `~datetime.date` field.

    This field behaves in a similar fashion to the `DateTime` field.
    """

    type = datetime.date

    def deserialize(self, value):
        """
        Deserialize the given string as a `~datetime.date`.

        Args:
            value (str): the string to deserialize.

        Returns:
            ~datetime.date: the deserialized date.
        """
        if self.format == 'iso8601':
            return isodate.parse_date(value)
        else:
            return datetime.datetime.strptime(value, self.format).date()


class Time(DateTime):
    """
    A `~datetime.time` field.

    This field behaves in a similar fashion to the `DateTime` field.
    """

    type = datetime.time

    def deserialize(self, value):
        """
        Deserialize the given string as a `~datetime.time`.

        Args:
            value (str): the string to deserialize.

        Returns:
            ~datetime.time: the deserialized date.
        """
        if self.format == 'iso8601':
            return isodate.parse_time(value)
        else:
            return datetime.datetime.strptime(value, self.format).time()


class Uuid(Instance):
    """
    A `~uuid.UUID` field.

    This field validates that the input data is an instance of `~uuid.UUID`. It
    serializes the UUID as a string, and deserializes strings as UUIDs.

    ::

        >>> class User(Model):
        ...     key = Uuid()

        >>> user = User.from_dict({'key': '6af21dcd-e479-4af6-a708-0cbc8e2438c1'})
        >>> user.key
        UUID('6af21dcd-e479-4af6-a708-0cbc8e2438c1')
        >>> user.to_dict()
        OrderedDict([('key', '6af21dcd-e479-4af6-a708-0cbc8e2438c1')])
        >>> User('not a uuid')
        Traceback (most recent call last):
        ...
        serde.exceptions.ValidationError: expected 'UUID' but got 'str'
    """

    def __init__(self, **kwargs):
        """
        Create a new Uuid.

        Args:
            **kwargs: keyword arguments for the `Field` constructor.
        """
        super(Uuid, self).__init__(uuid.UUID, **kwargs)

    def serialize(self, value):
        """
        Serialize the given UUID.

        Args:
            value (~uuid.UUID): the UUID to serialize.

        Returns:
            str: a string representation of the Uuid.
        """
        return str(value)

    def deserialize(self, value):
        """
        Deserialize the given string.

        Args:
            value (str): the string to deserialize.

        Returns:
            ~uuid.UUID: the deserialized Uuid.
        """
        return uuid.UUID(value)
