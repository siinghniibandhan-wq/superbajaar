export const executiveStructure = Object.freeze({
  ceo: Object.freeze({
    title: 'CEO',
    fullTitle: 'Chief Executive Officer',
    reports: Object.freeze([
      Object.freeze({ title: 'Chief Staff', fullTitle: 'Chief Staff', leadsDepartment: true }),
      Object.freeze({ title: 'CMO', fullTitle: 'Chief Marketing Officer', leadsDepartment: true }),
      Object.freeze({ title: 'CoS', fullTitle: 'Chief of Sales', leadsDepartment: true }),
      Object.freeze({ title: 'CTO', fullTitle: 'Chief Technology Officer', leadsDepartment: true }),
      Object.freeze({ title: 'CHR', fullTitle: 'Chief Human Resources', leadsDepartment: true }),
    ]),
  }),
});
