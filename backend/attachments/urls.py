from django.urls import path

from attachments import views

urlpatterns = [
    path("presign", views.PresignView.as_view()),
    path("<uuid:public_id>/complete", views.CompleteView.as_view()),
]
