import test from 'node:test';
import assert from 'node:assert/strict';
import { executiveStructure } from '../../src/features/hr/organisationStructure.js';

test('executive organisation structure preserves CEO and the five approved direct-report positions', () => {
  assert.equal(executiveStructure.ceo.title, 'CEO');
  assert.deepEqual(executiveStructure.ceo.reports.map(role => role.title), [
    'Chief Staff', 'CMO', 'CoS', 'CTO', 'CHR',
  ]);
  assert.ok(executiveStructure.ceo.reports.every(role => role.leadsDepartment === true));
});
