from django import forms


class UploadForm(forms.Form):
    file = forms.FileField(
        help_text="上传CSV文件，包含用户订单记录",
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
    )
    cluster_count = forms.IntegerField(
        required=False,
        min_value=2,
        max_value=12,
        initial=4,
        help_text="分群数，默认4",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    auto_k = forms.BooleanField(
        required=False,
        initial=False,
        help_text="自动选择K",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    k_min = forms.IntegerField(
        required=False,
        min_value=2,
        max_value=20,
        initial=2,
        help_text="K最小值",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    k_max = forms.IntegerField(
        required=False,
        min_value=2,
        max_value=20,
        initial=8,
        help_text="K最大值",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )

