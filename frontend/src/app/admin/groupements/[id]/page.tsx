"use client";

import { useParams } from "next/navigation";
import { GroupementDetail } from "@/components/groupement/groupement-detail";

export default function AdminGroupementDetailPage() {
  const { id } = useParams<{ id: string }>();
  return <GroupementDetail groupementId={id} backHref="/admin/groupements" />;
}
