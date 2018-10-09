"""
Serde - A framework for serializing and deserializing Python objects.
"""


from serde.error import DeserializationError, SerdeError, SerializationError, ValidationError
from serde.field import Bool, Dict, Field, Float, Int, List, ModelField, Str, Tuple, TypeField
from serde.model import Model


__all__ = ['Bool', 'DeserializationError', 'Dict', 'Field', 'Float', 'Int',
           'List', 'Model', 'ModelField', 'SerdeError', 'SerializationError',
           'Str', 'Tuple', 'TypeField', 'ValidationError']
__author__ = 'Ross MacArthur'
__email__ = 'macarthur.ross@gmail.com'
__version__ = '0.1.0'
