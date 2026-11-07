"use client";

// إدارة الموظفين — رفع صورة وجه (name/role/photo) + جدول بالقائمة والحذف
// القائمة تأتي من الـ server component؛ الحذف والإضافة يمران عبر server actions
// (revalidatePath يحدّث الجدول تلقائياً وReact 19 يصفّر النموذج بعد نجاح الإضافة)
import { useActionState, useState } from "react";

import {
  createEmployeeAction,
  deleteEmployeeAction,
  type EmployeeActionState,
} from "@/actions/employees";
import { useLanguage } from "@/components/language-context";

const initialState: EmployeeActionState = {};

interface EmployeeRow {
  id: number;
  name: string;
  role: string;
}

/** حقل نصي موحّد لاسم/وظيفة الموظف */
function TextField({
  fieldKey,
  label,
  placeholder,
  isPending,
}: {
  fieldKey: string;
  label: string;
  placeholder?: string;
  isPending: boolean;
}) {
  return (
    <div>
      <label
        htmlFor={fieldKey}
        className="block text-xs font-medium text-gray-300 mb-1"
      >
        {label}
      </label>
      <input
        id={fieldKey}
        name={fieldKey}
        type="text"
        autoComplete="off"
        placeholder={placeholder}
        disabled={isPending}
        className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white placeholder:text-gray-500 focus:border-teal-500 focus:outline-none"
      />
    </div>
  );
}

export default function EmployeesManager({
  employees,
}: {
  employees: EmployeeRow[];
}) {
  const { t } = useLanguage();
  const [state, formAction, isPending] = useActionState(
    createEmployeeAction,
    initialState
  );
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [listError, setListError] = useState<string | null>(null);

  const handleDelete = async (id: number) => {
    if (deletingId !== null) return;
    setListError(null);
    setDeletingId(id);
    const result = await deleteEmployeeAction(id);
    if (result.error) setListError(result.error);
    setDeletingId(null);
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold mb-2">{t("employeesTitle")}</h1>
        <p className="text-sm text-gray-400">{t("employeesHint")}</p>
      </div>

      {/* ===== إضافة موظف ===== */}
      <div className="rounded-xl border border-gray-800 bg-gray-800/60 p-6 shadow-xl space-y-3">
        <form
          action={formAction}
          autoComplete="off"
          className="space-y-3"
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <TextField
              fieldKey="name"
              label={t("employeeNameLabel")}
              placeholder={t("employeeNamePlaceholder")}
              isPending={isPending}
            />
            <TextField
              fieldKey="role"
              label={t("employeeRoleLabel")}
              placeholder={t("employeeRolePlaceholder")}
              isPending={isPending}
            />
          </div>
          <div>
            <label
              htmlFor="photo"
              className="block text-xs font-medium text-gray-300 mb-1"
            >
              {t("employeePhotoLabel")}
            </label>
            <input
              id="photo"
              name="photo"
              type="file"
              accept="image/*"
              disabled={isPending}
              dir="ltr"
              className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-300 file:mr-3 file:rounded file:border-0 file:bg-teal-600 file:px-3 file:py-1 file:text-white hover:file:bg-teal-700"
            />
          </div>

          {state.ok && (
            <p className="rounded-md border border-green-800 bg-green-900/40 px-3 py-2 text-sm text-green-300">
              {t("employeeAdded")}
            </p>
          )}
          {state.error && (
            <p className="rounded-md border border-red-800 bg-red-900/40 px-3 py-2 text-sm text-red-300">
              {state.error}
            </p>
          )}
          {listError && (
            <p className="rounded-md border border-red-800 bg-red-900/40 px-3 py-2 text-sm text-red-300">
              {listError}
            </p>
          )}

          <div className="pt-2">
            <button
              type="submit"
              disabled={isPending}
              className="h-11 rounded-md bg-teal-600 px-6 font-medium text-white hover:bg-teal-700 disabled:opacity-50"
            >
              {isPending ? t("adding") : t("addEmployee")}
            </button>
          </div>
        </form>
      </div>

      {/* ===== القائمة ===== */}
      <div className="rounded-xl border border-gray-800 bg-gray-800/60 p-6 shadow-xl">
        <div className="rounded-lg border border-gray-700 overflow-hidden">
          <div className="grid grid-cols-[minmax(0,2fr)_minmax(0,2fr)_auto] gap-3 bg-gray-900/80 px-4 py-2 text-xs text-gray-400">
            <span>{t("employeeColumn")}</span>
            <span>{t("roleColumn")}</span>
            <span className="text-right">{t("deleteEmployee")}</span>
          </div>

          {employees.length === 0 ? (
            <p className="px-4 py-4 text-xs text-gray-500">
              {t("noEmployees")}
            </p>
          ) : (
            <div className="divide-y divide-gray-700/60">
              {employees.map((employee) => (
                <div
                  key={employee.id}
                  className="grid grid-cols-[minmax(0,2fr)_minmax(0,2fr)_auto] gap-3 px-4 py-3 items-center"
                >
                  <span className="text-sm text-white font-medium truncate">
                    {employee.name}
                  </span>
                  <span className="text-sm text-gray-300 truncate">
                    {employee.role || "—"}
                  </span>
                  <button
                    type="button"
                    disabled={deletingId === employee.id || isPending}
                    aria-label={`${t("deleteEmployeeAria")} ${employee.name}`}
                    onClick={() => handleDelete(employee.id)}
                    className="h-9 rounded-md bg-red-900/50 px-3 text-sm text-red-300 hover:bg-red-900/80 disabled:opacity-50 whitespace-nowrap"
                  >
                    ✕{" "}
                    {deletingId === employee.id ? t("deleting") : t("deleteEmployee")}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
