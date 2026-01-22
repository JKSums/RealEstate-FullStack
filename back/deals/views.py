from rest_framework import generics, permissions
from rest_framework_simplejwt.authentication import JWTAuthentication
from .models import Sale, Commission, PendingSaleRequest
from .serializers import SaleSerializer, SaleCreateSerializer, CommissionSerializer, PendingSaleRequestSerializer
from listings.models import Property
from django.db import transaction
from decimal import Decimal
from django.contrib.auth.models import User


class IsPropertyOwnerOrAgent(permissions.BasePermission):
    """
    Custom permission to only allow property owner or assigned agent to create sales.
    """
    def has_permission(self, request, view):
        if request.method in ['POST']:
            # For creating sales, need to check if user is property owner or agent
            property_id = request.data.get('property_id')
            if property_id:
                try:
                    property_obj = Property.objects.get(pk=property_id)
                    return (request.user == property_obj.owner or
                           request.user == property_obj.agent)
                except Property.DoesNotExist:
                    return False
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # Allow read permissions for staff/admin
        if request.user.is_staff:
            return True
        # For object-level permissions (sale records), check against property
        if hasattr(obj, 'property'):
            return (request.user == obj.property.owner or
                   request.user == obj.property.agent)
        return False


class SaleListCreateView(generics.ListCreateAPIView):
    queryset = Sale.objects.all()
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsPropertyOwnerOrAgent]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return SaleCreateSerializer
        return SaleSerializer

    def get_queryset(self):
        if self.request.user.is_staff:
            return Sale.objects.all()
        from django.db.models import Q
        return Sale.objects.filter(
            Q(property__owner=self.request.user) | Q(property__agent=self.request.user)
        )

    def perform_create(self, serializer):
        with transaction.atomic():
            # The SaleCreateSerializer handles property_id -> property mapping in its create method
            # So at this point in perform_create, property_id has already been resolved to a Property object
            # Since we're in perform_create, the validated_data has the raw values
            property_id = serializer.validated_data.get('property_id')

            # In the SaleCreateSerializer, property_id is already a Property object after validation
            property_obj = property_id

            # Get final_price from validated_data
            final_price = serializer.validated_data['final_price']
            buyer = serializer.validated_data.get('buyer')

            # For your request, compare final_price with the property's set price
            property_set_price = property_obj.total_price()  # This uses the total_price method from Property model

            # Check for suspicious pricing conditions that require admin approval
            requires_admin_approval = False
            reason_for_review = ""

            # Compare final_price with property's set price (property.total_price())
            if final_price > property_set_price * Decimal('2.0'):
                requires_admin_approval = True
                reason_for_review = f"Final price ({final_price}) is more than 2x the property set price ({property_set_price})"
            elif final_price < property_set_price * Decimal('0.5'):
                requires_admin_approval = True
                reason_for_review = f"Final price ({final_price}) is less than half the property set price ({property_set_price})"

            if requires_admin_approval:
                # Create a pending sale request instead of completing the sale
                PendingSaleRequest.objects.create(
                    property=property_obj,
                    final_price=final_price,
                    proposed_buyer=buyer,
                    reason_for_review=reason_for_review,
                    created_by=self.request.user
                )

                # Set property status back to UNDER_REVIEW since sale is pending
                property_obj.status = 'UNDER_REVIEW'
                property_obj.save()
            else:
                # Complete the sale normally if no suspicious conditions
                sale_instance = serializer.save()

                # Update property status to SOLD
                property_obj.status = 'SOLD'
                property_obj.save()

                if property_obj.agent:
                    commission_rate = Decimal('5.00')
                    commission_amount = (sale_instance.final_price * commission_rate) / 100

                    Commission.objects.create(
                        sale=sale_instance,
                        agent=property_obj.agent,
                        commission_rate=commission_rate,
                        amount_calculated=commission_amount
                    )


class SaleDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Sale.objects.all()
    serializer_class = SaleSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsPropertyOwnerOrAgent]

    def get_queryset(self):
        if self.request.user.is_staff:
            return Sale.objects.all()
        from django.db.models import Q
        return Sale.objects.filter(
            Q(property__owner=self.request.user) | Q(property__agent=self.request.user)
        )


class CommissionListView(generics.ListAPIView):
    serializer_class = CommissionSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return Commission.objects.all()
        return Commission.objects.filter(agent=self.request.user)


class CommissionDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Commission.objects.all()
    serializer_class = CommissionSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return Commission.objects.all()
        return Commission.objects.filter(agent=self.request.user)


class PendingSaleRequestListView(generics.ListCreateAPIView):
    """
    List all pending sale requests for admin review
    """
    serializer_class = PendingSaleRequestSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return PendingSaleRequest.objects.filter(status='PENDING')


class PendingSaleRequestDetailView(generics.RetrieveUpdateAPIView):
    """
    Retrieve, approve, or reject a specific pending sale request
    """
    queryset = PendingSaleRequest.objects.all()
    serializer_class = PendingSaleRequestSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAdminUser]

    def perform_update(self, serializer):
        # When admin approves the request, create the actual sale
        instance = serializer.save()

        if instance.status == 'APPROVED':
            # Create the sale record
            property_obj = instance.property
            sale = Sale.objects.create(
                property=property_obj,
                date_sold=instance.created_at.date(),
                final_price=instance.final_price,
                buyer=instance.proposed_buyer,
                approval_status='APPROVED'
            )

            # Update property status to SOLD
            property_obj.status = 'SOLD'
            property_obj.save()

            # Calculate and create commission if agent exists
            if property_obj.agent:
                commission_rate = Decimal('5.00')
                commission_amount = (sale.final_price * commission_rate) / 100

                Commission.objects.create(
                    sale=sale,
                    agent=property_obj.agent,
                    commission_rate=commission_rate,
                    amount_calculated=commission_amount
                )

        elif instance.status == 'REJECTED':
            # When rejected, set the property back to active
            property_obj = instance.property
            property_obj.status = 'ACTIVE'
            property_obj.save()


class AdminSaleApprovalView(generics.UpdateAPIView):
    """
    For admin to approve or reject sales that require approval
    """
    queryset = Sale.objects.filter(approval_status='PENDING_REVIEW')
    serializer_class = SaleSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAdminUser]