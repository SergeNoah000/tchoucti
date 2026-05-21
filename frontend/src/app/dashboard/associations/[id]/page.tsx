"use client";

import { useParams } from "next/navigation";
import { AssociationDetail } from "@/components/association/association-detail";

export default function DashboardAssociationDetailPage() {
  const { id } = useParams<{ id: string }>();
  return <AssociationDetail associationId={id} backHref="/dashboard/associations" />;
}
