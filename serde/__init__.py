"""
Serde is a lightweight, general-purpose, ORM framework for defining,
serializing, deserializing, and validating data structures in Python.

Objects are defined by subclassing `~serde.model.Model` and assigning
`~serde.field.Field` attributes on the Model. In the following example `User` is
the subclassed `~serde.model.Model` with two fields `name` and `age`. The
`~serde.field.Str` and `~serde.field.Int` classes handle serialization,
deserialization, and validation for these attributes.

::

    >>> from serde import Model, field

    >>> class User(Model):
    ...     name = field.Str(rename='username')
    ...     age = field.Int(required=False)

Models are validated when they are instantiated and after they are deserialized.

::

    >>> user = User(name='Benedict Cumberbatch', age=42)
    >>> user.name
    'Benedict Cumberbatch'
    >>> user.age
    42

Models can be serialized and deserialized from different data formats. The most
basic format is primitive Python types. To do this we call the
`~serde.model.Model.to_dict()` method.

::

    >>> user.to_dict() # doctest: +SKIP
    {'username': 'Benedict Cumberbatch', 'age', 42}

To deserialize a Model we simply call the reciprocal method. For example to
deserialize a `User` from a dictionary we use the
`~serde.model.Model.from_dict()` method.

::

    >>> user = User.from_dict({'username': 'Idris Elba', 'age': 46})
    >>> user.name
    'Idris Elba'
    >>> user.age
    46

Other supported data formats including `JSON <serde.model.Model.to_json()>`,
`TOML <serde.model.Model.to_toml()>`, and `YAML <serde.model.Model.to_yaml()>`.
See `~serde.model` for more examples. Documentation for supported fields can be
found in `~serde.field`.
"""

from .error import DeserializationError, SerdeError, SerializationError, ValidationError
from .field import (
    Bool, Boolean, Choice, Dict, Dictionary, Domain, Email, Field, Float,
    Instance, Int, Integer, List, Nested, Slug, Str, String, Tuple, Url, Uuid
)
from .model import Model


__all__ = [
    'Bool', 'Boolean', 'Choice', 'DeserializationError', 'Dict', 'Dictionary', 'Domain', 'Email',
    'Field', 'Float', 'Instance', 'Int', 'Integer', 'List', 'Model', 'Nested', 'SerdeError',
    'SerializationError', 'Slug', 'Str', 'String', 'Tuple', 'Url', 'Uuid', 'ValidationError'
]
__author__ = 'Ross MacArthur'
__email__ = 'macarthur.ross@gmail.com'
__version__ = '0.1.2'
