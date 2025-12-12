from django import forms


class UploadForm(forms.Form):
    file = forms.FileField(help_text="上传CSV文件，包含用户订单记录")
    cluster_count = forms.IntegerField(
        required=False, min_value=2, max_value=12, initial=4, help_text="分群数，默认4"
    )

