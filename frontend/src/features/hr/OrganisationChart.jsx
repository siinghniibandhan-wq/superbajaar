import { executiveStructure } from './organisationStructure.js';

export default function OrganisationChart({ departments = [] }) {
  const { ceo } = executiveStructure;
  const activeDepartments = departments.filter(department => department.is_active !== false);

  return <section className="hr-panel hr-organisation" aria-labelledby="hr-organisation-title">
    <div>
      <h2 id="hr-organisation-title">Executive organisation structure</h2>
      <p className="hr-organisation-intro">The CEO leads the company. Chief Staff, CMO, CoS, CTO and CHR report to the CEO and each lead their assigned department.</p>
    </div>
    <div className="hr-org-ceo">
      <strong>{ceo.title}</strong>
      <span>{ceo.fullTitle}</span>
    </div>
    <div className="hr-org-connect" aria-hidden="true" />
    <div className="hr-org-reports">
      {ceo.reports.map(role => <article className="hr-org-role" key={role.title}>
        <strong>{role.title}</strong>
        <span>{role.fullTitle}</span>
        <small>Department head</small>
      </article>)}
    </div>
    <div className="hr-org-departments">
      <h3>Department directory</h3>
      {activeDepartments.length ? <div className="hr-org-department-list">{activeDepartments.map(department => <article key={department.id}>
        <strong>{department.name}</strong>
        <span>{department.employee_count ?? 0} employees</span>
        <small>Department head assignment: not configured</small>
      </article>)}</div> : <p>No active departments have been configured yet.</p>}
    </div>
    <p className="hr-org-governance">Executive titles are organisation positions, not login roles. This chart does not grant access. Department-head assignments and department/store/warehouse permissions must be configured separately before scope-based access can be enforced.</p>
  </section>;
}
