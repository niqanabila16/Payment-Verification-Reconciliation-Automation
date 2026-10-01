"""Shared form plumbing so every field renders with the same accessible markup."""
from django import forms


class StyledFormMixin:
    """
    Adds CSS classes and ARIA attributes to every widget:
      - aria-invalid="true" when the field has an error
      - aria-describedby pointing at the hint and error elements rendered by components/field.html
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
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
            described = []
            if field.help_text:
                described.append(f"hint-{self._field_id(name)}")
            if self.is_bound and name in self.errors:
                widget.attrs["aria-invalid"] = "true"
                described.append(f"error-{self._field_id(name)}")
            if described:
                widget.attrs["aria-describedby"] = " ".join(described)

    def _field_id(self, name: str) -> str:
        return self[name].auto_id.replace("id_", "") if self[name].auto_id else name
