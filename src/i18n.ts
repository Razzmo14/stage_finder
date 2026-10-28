import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en.json";
import fr from "./locales/fr.json";

export const LANGUAGES = ["en", "fr"] as const;
export type Language = (typeof LANGUAGES)[number];

const stored = localStorage.getItem("stage-finder-language");
const initial: Language = stored === "fr" || stored === "en" ? stored : "en";

i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    fr: { translation: fr },
  },
  lng: initial,
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

export function setLanguage(language: Language) {
  localStorage.setItem("stage-finder-language", language);
  void i18n.changeLanguage(language);
}

export default i18n;
