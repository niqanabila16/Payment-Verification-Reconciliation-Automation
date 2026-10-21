"""Shared form plumbing so every field renders with the same accessible markup."""
from django import forms


class StyledFormMixin:
    """
    Adds CSS classes and ARIA attributes to every widget:
      - aria-describedby pointing at the hint and error elements rendered by components/field.html
      - aria-invalid="true" when the field has an error (applied after validation runs)

    Errors are NOT read in __init__: subclasses (for example the receipt form) load their dropdown values
    from the database after calling super().__init__(), and validating earlier would use empty lists.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.help_text = ""          # the screens carry no explanatory text under the fields
            widget = field.widget
            css = widget.attrs.get("class", "")
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = f"{css} checkbox".strip()
            elif isinstance(widget, forms.Select):
                widget.attrs["class"] = f"{css} input input--select".strip()
            elif isinstance(widget, forms.Textarea):
                widget.attrs["class"] = f"{css} input input--textarea".strip()
            else:
                widget.attrs["class"] = f"{css} input".strip()
        self._apply_aria()

    def full_clean(self):
        super().full_clean()
        self._apply_aria()

    def _apply_aria(self):
        errors = self._errors or {}
        for name, field in self.fields.items():
            widget, key = field.widget, self._field_id(name)
            described = [f"hint-{key}"] if field.help_text else []
            if name in errors:
                widget.attrs["aria-invalid"] = "true"
                described.append(f"error-{key}")
            else:
                widget.attrs.pop("aria-invalid", None)
            if described:
                widget.attrs["aria-describedby"] = " ".join(described)
            else:
                widget.attrs.pop("aria-describedby", None)

    def _field_id(self, name: str) -> str:
        auto_id = self[name].auto_id
        return auto_id.replace("id_", "", 1) if auto_id else name
