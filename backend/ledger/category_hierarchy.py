"""Read the category tree of one owner.

The *family* of a category is the category, its descendants (children,
grandchildren and lower levels) and its ancestors. Two budgets in one family
count the same expenses, so planning rejects them in overlapping months and
the same currency. ``planning.models`` and ``planning.services`` use these
reads, and ``categories`` (layer 2) owns them, so the plan records do not
import a planning service (docs/v2/architecture.md#target-layers).

A *change validator* is a function that a higher layer registers here with
``register_change_validator``. ``Category.clean`` calls each one with the
category and its pending parent and type, before the save. Thus planning can
reject a change that would invalidate its limits, and ``categories`` does
not import ``planning``. ``planning.apps.PlanningConfig.ready`` registers the
budget check.
"""

from collections import defaultdict

from ledger.categories import Category

_change_validators = []


def register_change_validator(validator):
    """Register ``validator(category)``; it raises ``ValidationError`` to refuse a change.

    A validator that is already registered is not added again, so a second
    ``ready()`` call has no effect. Return ``validator``.
    """
    if validator not in _change_validators:
        _change_validators.append(validator)
    return validator


def run_change_validators(category):
    """Call each registered change validator in registration order."""
    for validator in tuple(_change_validators):
        validator(category)


def category_parents(user):
    """Return ``{category pk: parent pk or None}`` for the categories of ``user``."""
    return dict(Category.objects.filter(user=user).values_list("pk", "parent_category_id"))


def descendants(parents, category_id):
    """Return ``category_id`` and every category below it in ``parents``."""
    result = {category_id}
    pending = [category_id]
    children = defaultdict(list)
    for child, parent in parents.items():
        children[parent].append(child)
    while pending:
        for child in children[pending.pop()]:
            if child not in result:
                result.add(child)
                pending.append(child)
    return result


def category_family(user, category_id):
    """Categories which would overlap the selected category's budget."""
    parents = category_parents(user)
    result = descendants(parents, category_id)
    parent = parents.get(category_id)
    while parent and parent not in result:
        result.add(parent)
        parent = parents.get(parent)
    return result
