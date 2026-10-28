import { useTranslation } from "react-i18next";

export default function Overview() {
  const { t } = useTranslation();
  return (
    <div>
      <h2 className="text-xl font-semibold">{t("overview.title")}</h2>
      <p className="mt-2 text-neutral-500">{t("overview.pending")}</p>
    </div>
  );
}
