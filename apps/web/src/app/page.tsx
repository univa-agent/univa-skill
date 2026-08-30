import { redirect } from "next/navigation";
import type { Metadata } from "next";
import { SITE_URL } from "@/constants/site";

export const metadata: Metadata = {
  alternates: {
    canonical: SITE_URL,
  },
};

export default async function Home() {
  redirect("/projects");
}
