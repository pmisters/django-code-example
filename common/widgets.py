from django.forms import CheckboxSelectMultiple, Textarea


class EditorWidget(Textarea):
    template_name = "widgets/editor.html"


class FacilitiesWidget(CheckboxSelectMultiple):
    template_name = "widgets/facilities.html"
