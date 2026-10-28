import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";

interface ExperienceDto {
  company: string;
  position: string;
  start_date: string;
  end_date: string;
  description: string;
  skills: string[];
}
interface EducationDto {
  school: string;
  degree: string;
  field: string;
  start_date: string;
  end_date: string;
}
interface ProjectDto {
  name: string;
  description: string;
  url: string;
  skills: string[];
}
export interface ProfileDto {
  id: number;
  full_name: string;
  email: string;
  phone: string;
  location: string;
  headline: string;
  summary: string;
  skills: string[];
  languages: string[];
  base_letter: string;
  letter_tone: string;
  letter_language: string;
  never_say_rules: string[];
  experiences: ExperienceDto[];
  education: EducationDto[];
  projects: ProjectDto[];
}

const EMPTY: ProfileDto = {
  id: 0,
  full_name: "",
  email: "",
  phone: "",
  location: "",
  headline: "",
  summary: "",
  skills: [],
  languages: [],
  base_letter: "",
  letter_tone: "",
  letter_language: "",
  never_say_rules: [],
  experiences: [],
  education: [],
  projects: [],
};

function Field({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="block text-sm">
      <span className="text-neutral-600">{label}</span>
      <input
        className="mt-1 w-full rounded border border-neutral-300 px-2 py-1"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

function Area({
  label,
  value,
  onChange,
  rows = 4,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  rows?: number;
}) {
  return (
    <label className="block text-sm">
      <span className="text-neutral-600">{label}</span>
      <textarea
        className="mt-1 w-full rounded border border-neutral-300 px-2 py-1"
        rows={rows}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

function ListField({
  label,
  items,
  onChange,
}: {
  label: string;
  items: string[];
  onChange: (v: string[]) => void;
}) {
  return (
    <label className="block text-sm">
      <span className="text-neutral-600">{label} (comma separated)</span>
      <input
        className="mt-1 w-full rounded border border-neutral-300 px-2 py-1"
        value={items.join(", ")}
        onChange={(e) => onChange(e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
      />
    </label>
  );
}

export default function ProfilePage() {
  const queryClient = useQueryClient();

  const profile = useQuery<ProfileDto>({
    queryKey: ["profile"],
    queryFn: () => api.get<ProfileDto>("/api/v1/profile"),
  });

  const save = useMutation({
    mutationFn: (payload: ProfileDto) =>
      api.put<ProfileDto>("/api/v1/profile", payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["profile"] }),
  });

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const { invoke } = await import("@tauri-apps/api/core");
      const backendUrl = await invoke<string>("get_backend_url");
      const token = await invoke<string>("get_session_token");
      const body = new FormData();
      body.append("file", file);
      const response = await fetch(`${backendUrl}/api/v1/profile/cv`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body,
      });
      if (!response.ok) throw new Error(await response.text());
      return (await response.json()) as ProfileDto;
    },
    onSuccess: (draft) => {
      save.mutate({ ...draft, id: 0 });
    },
  });

  if (profile.isLoading) return <p className="text-neutral-500">Loading profile...</p>;

  const data: ProfileDto = profile.data ?? EMPTY;
  const set = <K extends keyof ProfileDto>(key: K, value: ProfileDto[K]) => {
    save.mutate({ ...data, [key]: value } as ProfileDto);
  };

  return (
    <div className="max-w-3xl space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Profile</h2>
        <label className="cursor-pointer rounded border border-neutral-300 px-3 py-1 text-sm">
          Import CV (PDF/DOCX)
          <input
            type="file"
            accept=".pdf,.docx"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) upload.mutate(file);
            }}
          />
        </label>
      </div>
      {upload.isPending && <p className="text-sm">Extracting profile from CV...</p>}
      {upload.isError && <p className="text-sm text-red-600">{upload.error.message}</p>}
      {save.isError && <p className="text-sm text-red-600">{save.error.message}</p>}

      <div className="grid grid-cols-2 gap-4 rounded border border-neutral-200 bg-white p-4">
        <Field label="Full name" value={data.full_name} onChange={(v) => set("full_name", v)} />
        <Field label="Email" value={data.email} onChange={(v) => set("email", v)} />
        <Field label="Phone" value={data.phone} onChange={(v) => set("phone", v)} />
        <Field label="Location" value={data.location} onChange={(v) => set("location", v)} />
        <Field label="Headline" value={data.headline} onChange={(v) => set("headline", v)} />
        <ListField label="Languages" items={data.languages} onChange={(v) => set("languages", v)} />
        <div className="col-span-2">
          <Area label="Summary" value={data.summary} onChange={(v) => set("summary", v)} />
        </div>
        <div className="col-span-2">
          <ListField label="Skills" items={data.skills} onChange={(v) => set("skills", v)} />
        </div>
      </div>

      <div className="rounded border border-neutral-200 bg-white p-4">
        <h3 className="font-semibold">Base cover letter</h3>
        <div className="mt-2 grid grid-cols-2 gap-4">
          <Field label="Tone" value={data.letter_tone} onChange={(v) => set("letter_tone", v)} />
          <Field
            label="Letter language"
            value={data.letter_language}
            onChange={(v) => set("letter_language", v)}
          />
        </div>
        <div className="mt-2">
          <Area
            label="Letter text"
            rows={6}
            value={data.base_letter}
            onChange={(v) => set("base_letter", v)}
          />
        </div>
        <div className="mt-2">
          <ListField
            label="Never-say rules"
            items={data.never_say_rules}
            onChange={(v) => set("never_say_rules", v)}
          />
        </div>
      </div>

      <div className="rounded border border-neutral-200 bg-white p-4">
        <h3 className="font-semibold">
          Experiences ({data.experiences.length}) — edit via CV import or API for now
        </h3>
        <ul className="mt-2 space-y-1 text-sm">
          {data.experiences.map((e, i) => (
            <li key={i}>
              <span className="font-medium">{e.position}</span> at {e.company} ({e.start_date} –{" "}
              {e.end_date || "now"})
            </li>
          ))}
        </ul>
        <h3 className="mt-4 font-semibold">Education ({data.education.length})</h3>
        <ul className="mt-2 space-y-1 text-sm">
          {data.education.map((e, i) => (
            <li key={i}>
              {e.degree} {e.field} — {e.school}
            </li>
          ))}
        </ul>
        <h3 className="mt-4 font-semibold">Projects ({data.projects.length})</h3>
        <ul className="mt-2 space-y-1 text-sm">
          {data.projects.map((p, i) => (
            <li key={i}>
              <span className="font-medium">{p.name}</span> — {p.description}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
