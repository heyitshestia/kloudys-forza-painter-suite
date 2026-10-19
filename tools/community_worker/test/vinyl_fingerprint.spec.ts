import { describe, expect, it } from 'vitest';
import { fingerprintShape, vinylFingerprint } from '../src/vinyl_fingerprint';
import type { CanonicalDesign, CanonicalShape } from '../src/types';

const native = (): CanonicalShape => ({ type: 1048677, data: [1, 2, 30, 40], color: [50, 60, 70, 255] });
const design = (shapes: CanonicalShape[]): CanonicalDesign => ({ format: 'kfps.community.v1',
  metadata: { shape_count: shapes.length, source_format: 'shapes', source_schema: 'forza-typecode', schema_known: true, detected_games: [] }, shapes });
const hash = async (shapes: CanonicalShape[]) => (await vinylFingerprint(design(shapes))).fingerprint;

describe('bounded render-semantic contribution fingerprints', () => {
  it('ignores wrappers/provenance but normalizes rotation/skew/alpha/mask defaults', async () => {
    const a = native(), b = native(); b.data.push(0, -0, 0); b.color.pop();
    expect(await hash([a])).toBe(await hash([b]));
    const other = design([a]); other.metadata.source_format = 'array'; other.metadata.source_schema = 'kfps-community';
    expect((await vinylFingerprint(other)).fingerprint).toBe(await hash([a]));
  });
  it('uses full type, explicit identity, then built-in word in the native resolver order', async () => {
    const a = native(), b = { ...native(), type: 0, resource_family: 'Primitives', resource_index: 1 };
    const c = { ...native(), type: 0, type_word: 1048677 & 65535 };
    expect(await hash([a])).toBe(await hash([b])); expect(await hash([a])).toBe(await hash([c]));
    expect(await hash([{ ...a, resource_family: 'Wrong', resource_index: 999, type_word: 3 }])).toBe(await hash([a]));
  });
  it('preserves geometry, color, mask, identity and layer order', async () => {
    const a = native();
    for (let i = 0; i < 6; i++) {
      const b = native(); b.data = [1, 2, 30, 40, 0, 0]; b.data[i]! += .001;
      expect(await hash([a])).not.toBe(await hash([b]));
    }
    expect(await hash([a])).not.toBe(await hash([{ ...a, type: 1048678 }]));
    expect(await hash([a])).not.toBe(await hash([{ ...a, mask: true }]));
    expect(await hash([a])).not.toBe(await hash([{ ...a, color: [50, 60, 71, 255] }]));
    const b = { ...a, type: 1048678 };
    expect(await hash([a, b])).not.toBe(await hash([b, a]));
  });
  it('fails closed on contradictory mask semantics and keeps primitive dialect distinct', async () => {
    const a = { ...native(), data: [1, 2, 30, 40, 0, 0, 1], mask: false };
    expect(await vinylFingerprint(design([a]))).toMatchObject({status:'review_required',fingerprint:null});
    expect(await hash([{ ...native(), type: 1 }])).not.toBe(await hash([native()]));
  });
  it('does not award distinct identities for invisible native padding, mask RGB or ignored rectangle rotation',async()=>{
    const a=native();
    const base=await hash([a]);
    const mask={...native(),mask:true,data:[1,2,3,4,0,0,1]};
    const masked=await hash([a,mask]);
    const rect={type:1,data:[10,20,30,40,0],color:[200,50,70,255]};
    const rectangle=await hash([rect]);
    for (let i=0;i<10;i++) {
      expect(await hash([a,{...native(),data:[i,0,1,1],color:[120,40,80,0]}])).toBe(base);
      expect(await hash([a,{...mask,color:[i,80,40,255]}])).toBe(masked);
      expect(await hash([{...rect,data:[10,20,30,40,i]}])).toBe(rectangle);
    }
    expect(await vinylFingerprint(design([{...native(),color:[120,40,80,0]}]))).toMatchObject({status:'review_required'});
    expect(await vinylFingerprint(design([{...rect,color:[120,40,80,0]},a]))).toMatchObject({status:'review_required'});
  });
  it('fails closed for unresolved resources, arbitrary tails and fractional colors', async () => {
    for (const shape of [{ ...native(), type: 999999 }, { ...native(), data: [0,0,1,1,0,0,0,42] },
      { ...native(), color: [.2, 2, 3, 255] }, { ...native(), source_format: 'unreviewed' }]) {
      expect(fingerprintShape(shape)).toBeNull();
      expect(await vinylFingerprint(design([shape]))).toMatchObject({ status: 'review_required', fingerprint: null });
    }
  });
  it('never discards active zero-alpha masks or guesses fractional mask flags',async()=>{
    const a=native();
    for (const alpha of [0,1,2,128,254]) {
      const mask={...a,mask:true,data:[0,0,.5,.5,0,0,1],color:[10,80,40,alpha]};
      expect(await vinylFingerprint(design([a,mask]))).toMatchObject({status:'review_required',fingerprint:null});
    }
    for (const flag of [-1,.5,2]) for (const explicit of [undefined,false,true]) {
      const mask={...a,data:[0,0,1,1,0,0,flag],...(explicit===undefined?{}:{mask:explicit})};
      expect(await vinylFingerprint(design([a,mask]))).toMatchObject({status:'review_required',fingerprint:null});
    }
    expect(await hash([a,{...a,mask:true}])).not.toBe(await hash([a]));
  });
});
