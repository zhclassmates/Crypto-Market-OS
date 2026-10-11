import assert from "node:assert/strict";
import {test} from "node:test";
import {revisionCache} from "./wm-unified-cache.ts";
test("coverage cached by committed snapshot; new revision and database invalidate",()=>{
 const cached=revisionCache<number>();let calls=0;const read=()=>++calls;
 assert.equal(cached('db:r1',read),1);assert.equal(cached('db:r1',read),1);
 assert.equal(cached('db:r2',read),2);assert.equal(cached('other:r2',read),3);
});
