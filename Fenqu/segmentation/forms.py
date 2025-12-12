from django import forms


class UploadFileForm(forms.Form):
    file = forms.FileField()


class RuleSegmentationForm(forms.Form):
    age_min = forms.IntegerField(required=False)
    age_max = forms.IntegerField(required=False)
    gender = forms.ChoiceField(
        required=False,
        choices=(
            ("", "Any"),
            ("male", "Male"),
            ("female", "Female"),
            ("other", "Other"),
        ),
    )
    region = forms.CharField(required=False)
    purchase_count_min = forms.IntegerField(required=False)
    purchase_count_max = forms.IntegerField(required=False)
    total_amount_min = forms.DecimalField(required=False, max_digits=12, decimal_places=2)
    total_amount_max = forms.DecimalField(required=False, max_digits=12, decimal_places=2)
    last_channel = forms.CharField(required=False)


class RFMSegmentationForm(forms.Form):
    recency_bins = forms.IntegerField(initial=3, min_value=2, max_value=9)
    frequency_bins = forms.IntegerField(initial=3, min_value=2, max_value=9)
    monetary_bins = forms.IntegerField(initial=3, min_value=2, max_value=9)


class ClusterSegmentationForm(forms.Form):
    n_clusters = forms.IntegerField(initial=3, min_value=2, max_value=12)
    use_features = forms.MultipleChoiceField(
        choices=(
            ("purchase_count", "Purchase Count"),
            ("total_amount", "Total Amount"),
            ("recency", "Recency (days since last purchase)"),
            ("last_login", "Last Login (days)"),
        ),
        initial=["purchase_count", "total_amount", "recency"],
        widget=forms.CheckboxSelectMultiple,
    )

