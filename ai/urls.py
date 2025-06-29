
from django.urls import path
from .views import analyze_essay_view,change_essay_type_view , compare_essays_view

urlpatterns = [
    path('analyze/', change_essay_type_view),
    # path('download/', download_revision),
    path('analyze_essay_view/', analyze_essay_view),
   
    path('compare_documents/', compare_essays_view),
]
