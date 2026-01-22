from django.db import models
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User


# Create your models here.
class Tour(models.Model):
    property = models.ForeignKey('listings.Property', on_delete=models.CASCADE, related_name='tours')
    agent = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='tours_as_agent')
    buyer = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='tours_as_buyer')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    TOUR_STATUS_CHOICES = [
        ("Scheduled", "Scheduled"),
        ("Completed", "Completed"),
        ("Cancelled", "Cancelled")
    ]
    status = models.CharField(max_length=10, choices=TOUR_STATUS_CHOICES, default="Scheduled")



    def clean(self):
        if self.property:
            overlapping_property_tours = Tour.objects.filter(
                property=self.property,
                start_time__lt=self.end_time,
                end_time__gt=self.start_time
            )

            if self.pk:
                overlapping_property_tours = overlapping_property_tours.exclude(pk=self.pk)

            if overlapping_property_tours.exists():
                raise ValidationError("This property already has a tour scheduled during this time period.")

        if self.agent:
            overlapping_agent_tours = Tour.objects.filter(
                agent=self.agent,
                start_time__lt=self.end_time,
                end_time__gt=self.start_time
            )

            if self.pk:
                overlapping_agent_tours = overlapping_agent_tours.exclude(pk=self.pk)

            if overlapping_agent_tours.exists():
                raise ValidationError("This agent already has a tour scheduled during this time period.")

        if self.start_time >= self.end_time:
            raise ValidationError("Start time cannot be greater than or equal to end time.")

    def __str__(self):
        agent_info = f" with {self.agent.get_full_name() or self.agent.username}" if self.agent else ""
        buyer_info = f" for {self.buyer.get_full_name() or self.buyer.username}" if self.buyer else ""
        start_time_formatted = self.start_time.strftime("%B %d, %Y at %I:%M %p")
        end_time_formatted = self.end_time.strftime("%I:%M %p")
        return f"Tour of {self.property.property_name}{agent_info}{buyer_info} on {start_time_formatted} - {end_time_formatted}"
