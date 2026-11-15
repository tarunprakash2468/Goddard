FeatureScript 3112;
import(path : "onshape/std/geometry.fs", version : "3112.0");

annotation { "Feature Type Name" : "Goddard Rocket Airframe" }
export const goddardRocketAirframe = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        annotation { "Name" : "Body Radius" }
        isLength(definition.bodyRadius, { (millimeter) : [1, 63.5, 10000] } as LengthBoundSpec);

        annotation { "Name" : "Body Length" }
        isLength(definition.bodyLength, { (meter) : [0.1, 1.2, 100] } as LengthBoundSpec);

        annotation { "Name" : "Nose Length" }
        isLength(definition.noseLength, { (meter) : [0.05, 0.55, 30] } as LengthBoundSpec);

        annotation { "Name" : "Stage Count" }
        isInteger(definition.stageCount, { (unitless) : [1, 1, 3] } as IntegerBoundSpec);

        annotation { "Name" : "Stage 2 Length" }
        isLength(definition.stage2Length, { (meter) : [0.05, 0.8, 50] } as LengthBoundSpec);

        annotation { "Name" : "Stage 2 Radius" }
        isLength(definition.stage2Radius, { (millimeter) : [1, 63.5, 10000] } as LengthBoundSpec);

        annotation { "Name" : "Interstage Length" }
        isLength(definition.interstageLength, { (meter) : [0.01, 0.15, 10] } as LengthBoundSpec);

        annotation { "Name" : "Has Fins" }
        definition.hasFins is boolean;

        annotation { "Name" : "Fin Count" }
        isInteger(definition.finCount, { (unitless) : [0, 4, 12] } as IntegerBoundSpec);

        annotation { "Name" : "Fin Root Chord" }
        isLength(definition.finRootChord, { (meter) : [0.01, 0.30, 10] } as LengthBoundSpec);

        annotation { "Name" : "Fin Tip Chord" }
        isLength(definition.finTipChord, { (meter) : [0.01, 0.12, 10] } as LengthBoundSpec);

        annotation { "Name" : "Fin Span" }
        isLength(definition.finSpan, { (meter) : [0.001, 0.14, 10] } as LengthBoundSpec);

        annotation { "Name" : "Fin Thickness" }
        isLength(definition.finThickness, { (millimeter) : [0.5, 4.0, 100] } as LengthBoundSpec);

        annotation { "Name" : "Engine Count" }
        isInteger(definition.engineCount, { (unitless) : [1, 1, 37] } as IntegerBoundSpec);

        annotation { "Name" : "Nozzle Exit Radius" }
        isLength(definition.nozzleExitRadius, { (millimeter) : [1, 25, 3000] } as LengthBoundSpec);

        annotation { "Name" : "Nozzle Length" }
        isLength(definition.nozzleLength, { (millimeter) : [1, 50, 10000] } as LengthBoundSpec);
    }
    {
        var r1 = definition.bodyRadius;
        var Lb1 = definition.bodyLength;
        var Ln = definition.noseLength;
        var stageCount = definition.stageCount;
        var hasFins = definition.hasFins;
        var nEngines = definition.engineCount;
        var rNozNom = definition.nozzleExitRadius;
        var LNoz = definition.nozzleLength;

        var r2 = definition.stage2Radius;
        var Lb2 = definition.stage2Length;
        var Linter = definition.interstageLength;

        var cr = definition.finRootChord;
        var ct = definition.finTipChord;
        var s = definition.finSpan;
        var t = definition.finThickness;
        var nFins = definition.finCount;

        var tipR = 1.5 * millimeter;

        // 1. Revolve Rocket Body around Z-axis
        var bodySketchId = id + "bodySketch";
        var bSketch = newSketch(context, bodySketchId, {
            "sketchPlane" : qCreatedBy(makeId("Front"), EntityType.FACE)
        });

        skLineSegment(bSketch, "baseLine", {
            "start" : vector(0, 0) * meter,
            "end" : vector(r1 / meter, 0) * meter
        });

        if (stageCount > 1)
        {
            skLineSegment(bSketch, "s1Line", {
                "start" : vector(r1 / meter, 0) * meter,
                "end" : vector(r1 / meter, Lb1 / meter) * meter
            });
            skLineSegment(bSketch, "interLine", {
                "start" : vector(r1 / meter, Lb1 / meter) * meter,
                "end" : vector(r2 / meter, (Lb1 + Linter) / meter) * meter
            });
            skLineSegment(bSketch, "s2Line", {
                "start" : vector(r2 / meter, (Lb1 + Linter) / meter) * meter,
                "end" : vector(r2 / meter, (Lb1 + Linter + Lb2) / meter) * meter
            });
            var zTop = Lb1 + Linter + Lb2;
            skLineSegment(bSketch, "noseLine", {
                "start" : vector(r2 / meter, zTop / meter) * meter,
                "end" : vector(tipR / meter, (zTop + Ln) / meter) * meter
            });
            skLineSegment(bSketch, "tipCapLine", {
                "start" : vector(tipR / meter, (zTop + Ln) / meter) * meter,
                "end" : vector(0, (zTop + Ln) / meter) * meter
            });
            skLineSegment(bSketch, "centerLine", {
                "start" : vector(0, (zTop + Ln) / meter) * meter,
                "end" : vector(0, 0) * meter
            });
        }
        else
        {
            skLineSegment(bSketch, "cylinderLine", {
                "start" : vector(r1 / meter, 0) * meter,
                "end" : vector(r1 / meter, Lb1 / meter) * meter
            });
            skLineSegment(bSketch, "noseLine", {
                "start" : vector(r1 / meter, Lb1 / meter) * meter,
                "end" : vector(tipR / meter, (Lb1 + Ln) / meter) * meter
            });
            skLineSegment(bSketch, "tipCapLine", {
                "start" : vector(tipR / meter, (Lb1 + Ln) / meter) * meter,
                "end" : vector(0, (Lb1 + Ln) / meter) * meter
            });
            skLineSegment(bSketch, "centerLine", {
                "start" : vector(0, (Lb1 + Ln) / meter) * meter,
                "end" : vector(0, 0) * meter
            });
        }

        skSolve(bSketch);

        opRevolve(context, id + "revolveBody", {
            "entities" : qSketchRegion(bodySketchId),
            "axis" : line(vector(0, 0, 0) * meter, vector(0, 0, 1)),
            "angleForward" : 360 * degree
        });

        // 2. Extrude base trapezoidal fins (only if hasFins is true and nFins > 0)
        if (hasFins && nFins > 0)
        {
            var finSketchId = id + "finSketch";
            var fSketch = newSketch(context, finSketchId, {
                "sketchPlane" : qCreatedBy(makeId("Front"), EntityType.FACE)
            });

            var overlapFin = 2.0 * millimeter;
            var z0 = 20.0 * millimeter;
            var r_in = r1 - overlapFin;
            var r_out = r1 + s;
            var sweepZ = (cr - ct) * 0.35;

            skLineSegment(fSketch, "f1", {
                "start" : vector(r_in / meter, z0 / meter) * meter,
                "end" : vector(r_out / meter, (z0 + sweepZ) / meter) * meter
            });
            skLineSegment(fSketch, "f2", {
                "start" : vector(r_out / meter, (z0 + sweepZ) / meter) * meter,
                "end" : vector(r_out / meter, (z0 + sweepZ + ct) / meter) * meter
            });
            skLineSegment(fSketch, "f3", {
                "start" : vector(r_out / meter, (z0 + sweepZ + ct) / meter) * meter,
                "end" : vector(r_in / meter, (z0 + cr) / meter) * meter
            });
            skLineSegment(fSketch, "f4", {
                "start" : vector(r_in / meter, (z0 + cr) / meter) * meter,
                "end" : vector(r_in / meter, z0 / meter) * meter
            });
            skSolve(fSketch);

            opExtrude(context, id + "extrudeFin", {
                "entities" : qSketchRegion(finSketchId),
                "direction" : vector(0, 1, 0),
                "endBound" : BoundingType.BLIND,
                "endDepth" : t / 2,
                "startBound" : BoundingType.BLIND,
                "startDepth" : t / 2
            });

            if (nFins > 1)
            {
                var transformsFins = [];
                var instanceNamesFins = [];
                for (var i = 1; i < nFins; i += 1)
                {
                    var angle = i * 360 * degree / nFins;
                    var rot = rotationAround(line(vector(0, 0, 0) * meter, vector(0, 0, 1)), angle);
                    transformsFins = append(transformsFins, rot);
                    instanceNamesFins = append(instanceNamesFins, "fin_" ~ i);
                }

                opPattern(context, id + "patternFins", {
                    "entities" : qCreatedBy(id + "extrudeFin", EntityType.BODY),
                    "transforms" : transformsFins,
                    "instanceNames" : instanceNamesFins
                });
            }
        }

        // 3. Concentric Multi-Engine Clusters
        var overlapNoz = 0.005 * meter;
        if (nEngines == 1)
        {
            var maxR1 = r1 * 0.70;
            var rNoz1 = rNozNom > maxR1 ? maxR1 : rNozNom;
            var rThroat1 = rNoz1 * 0.50;

            var cSkId = id + "centerNozSk";
            var cSk = newSketch(context, cSkId, {"sketchPlane" : qCreatedBy(makeId("Front"), EntityType.FACE)});
            skLineSegment(cSk, "cAxis", {"start" : vector(0, overlapNoz / meter) * meter, "end" : vector(0, -LNoz / meter) * meter});
            skLineSegment(cSk, "cExit", {"start" : vector(0, -LNoz / meter) * meter, "end" : vector(rNoz1 / meter, -LNoz / meter) * meter});
            skLineSegment(cSk, "cWall", {"start" : vector(rNoz1 / meter, -LNoz / meter) * meter, "end" : vector(rThroat1 / meter, overlapNoz / meter) * meter});
            skLineSegment(cSk, "cTop", {"start" : vector(rThroat1 / meter, overlapNoz / meter) * meter, "end" : vector(0, overlapNoz / meter) * meter});
            skSolve(cSk);
            opRevolve(context, id + "revCenterNoz", {
                "entities" : qSketchRegion(cSkId),
                "axis" : line(vector(0, 0, 0) * meter, vector(0, 0, 1)),
                "angleForward" : 360 * degree
            });
        }
        else if (nEngines <= 9)
        {
            // 1 center nozzle + 1 outer ring of (nEngines - 1) nozzles (Falcon 9 Octaweb layout)
            var nOuterRing = nEngines - 1;
            var rOuterRing = 0.65 * r1;
            var maxNozOuter = (rOuterRing * 3.14159 / nOuterRing) * 0.85;
            var rNoz = rNozNom > maxNozOuter ? maxNozOuter : rNozNom;
            var rThroat = rNoz * 0.50;

            // Center nozzle
            var cSkId = id + "centerNozSk";
            var cSk = newSketch(context, cSkId, {"sketchPlane" : qCreatedBy(makeId("Front"), EntityType.FACE)});
            skLineSegment(cSk, "cAxis", {"start" : vector(0, overlapNoz / meter) * meter, "end" : vector(0, -LNoz / meter) * meter});
            skLineSegment(cSk, "cExit", {"start" : vector(0, -LNoz / meter) * meter, "end" : vector(rNoz / meter, -LNoz / meter) * meter});
            skLineSegment(cSk, "cWall", {"start" : vector(rNoz / meter, -LNoz / meter) * meter, "end" : vector(rThroat / meter, overlapNoz / meter) * meter});
            skLineSegment(cSk, "cTop", {"start" : vector(rThroat / meter, overlapNoz / meter) * meter, "end" : vector(0, overlapNoz / meter) * meter});
            skSolve(cSk);
            opRevolve(context, id + "revCenterNoz", {
                "entities" : qSketchRegion(cSkId),
                "axis" : line(vector(0, 0, 0) * meter, vector(0, 0, 1)),
                "angleForward" : 360 * degree
            });

            // Outer ring base nozzle
            var oSkId = id + "ringNozSk";
            var oSk = newSketch(context, oSkId, {"sketchPlane" : qCreatedBy(makeId("Front"), EntityType.FACE)});
            skLineSegment(oSk, "oAxis", {"start" : vector(rOuterRing / meter, overlapNoz / meter) * meter, "end" : vector(rOuterRing / meter, -LNoz / meter) * meter});
            skLineSegment(oSk, "oExit", {"start" : vector(rOuterRing / meter, -LNoz / meter) * meter, "end" : vector((rOuterRing + rNoz) / meter, -LNoz / meter) * meter});
            skLineSegment(oSk, "oWall", {"start" : vector((rOuterRing + rNoz) / meter, -LNoz / meter) * meter, "end" : vector((rOuterRing + rThroat) / meter, overlapNoz / meter) * meter});
            skLineSegment(oSk, "oTop", {"start" : vector((rOuterRing + rThroat) / meter, overlapNoz / meter) * meter, "end" : vector(rOuterRing / meter, overlapNoz / meter) * meter});
            skSolve(oSk);
            opRevolve(context, id + "revRingNozBase", {
                "entities" : qSketchRegion(oSkId),
                "axis" : line(vector(rOuterRing / meter, 0, 0) * meter, vector(0, 0, 1)),
                "angleForward" : 360 * degree
            });

            var transformsOcta = [];
            var namesOcta = [];
            for (var i = 1; i < nOuterRing; i += 1)
            {
                var angle = i * 360 * degree / nOuterRing;
                transformsOcta = append(transformsOcta, rotationAround(line(vector(0, 0, 0) * meter, vector(0, 0, 1)), angle));
                namesOcta = append(namesOcta, "noz_octa_" ~ i);
            }
            opPattern(context, id + "patternOcta", {
                "entities" : qCreatedBy(id + "revRingNozBase", EntityType.BODY),
                "transforms" : transformsOcta,
                "instanceNames" : namesOcta
            });
        }
        else
        {
            // 10 to 37 engines: 1 center + inner ring (up to 12 at 0.42*r1) + outer ring (remaining at 0.78*r1)
            var nInner = 10;
            if (nEngines > 28)
            {
                nInner = 10; // e.g. 1 center + 10 inner + 22 outer = 33
            }
            else if (nEngines > 20)
            {
                nInner = 8;
            }
            else
            {
                nInner = floor((nEngines - 1) / 3);
            }
            var nOuter = nEngines - 1 - nInner;

            var rInner = 0.42 * r1;
            var rOuter = 0.78 * r1;

            var maxOuterNoz = (rOuter * 3.14159 / nOuter) * 0.85;
            var maxInnerNoz = (rInner * 3.14159 / nInner) * 0.85;
            var maxR = maxOuterNoz < maxInnerNoz ? maxOuterNoz : maxInnerNoz;
            var rNoz = rNozNom > maxR ? maxR : rNozNom;
            var rThroat = rNoz * 0.50;

            // Center nozzle
            var cSkId = id + "centerNozSk";
            var cSk = newSketch(context, cSkId, {"sketchPlane" : qCreatedBy(makeId("Front"), EntityType.FACE)});
            skLineSegment(cSk, "cAxis", {"start" : vector(0, overlapNoz / meter) * meter, "end" : vector(0, -LNoz / meter) * meter});
            skLineSegment(cSk, "cExit", {"start" : vector(0, -LNoz / meter) * meter, "end" : vector(rNoz / meter, -LNoz / meter) * meter});
            skLineSegment(cSk, "cWall", {"start" : vector(rNoz / meter, -LNoz / meter) * meter, "end" : vector(rThroat / meter, overlapNoz / meter) * meter});
            skLineSegment(cSk, "cTop", {"start" : vector(rThroat / meter, overlapNoz / meter) * meter, "end" : vector(0, overlapNoz / meter) * meter});
            skSolve(cSk);
            opRevolve(context, id + "revCenterNoz", {
                "entities" : qSketchRegion(cSkId),
                "axis" : line(vector(0, 0, 0) * meter, vector(0, 0, 1)),
                "angleForward" : 360 * degree
            });

            // Inner Ring Nozzle
            var iSkId = id + "innerNozSk";
            var iSk = newSketch(context, iSkId, {"sketchPlane" : qCreatedBy(makeId("Front"), EntityType.FACE)});
            skLineSegment(iSk, "iAxis", {"start" : vector(rInner / meter, overlapNoz / meter) * meter, "end" : vector(rInner / meter, -LNoz / meter) * meter});
            skLineSegment(iSk, "iExit", {"start" : vector(rInner / meter, -LNoz / meter) * meter, "end" : vector((rInner + rNoz) / meter, -LNoz / meter) * meter});
            skLineSegment(iSk, "iWall", {"start" : vector((rInner + rNoz) / meter, -LNoz / meter) * meter, "end" : vector((rInner + rThroat) / meter, overlapNoz / meter) * meter});
            skLineSegment(iSk, "iTop", {"start" : vector((rInner + rThroat) / meter, overlapNoz / meter) * meter, "end" : vector(rInner / meter, overlapNoz / meter) * meter});
            skSolve(iSk);
            opRevolve(context, id + "revInnerBase", {
                "entities" : qSketchRegion(iSkId),
                "axis" : line(vector(rInner / meter, 0, 0) * meter, vector(0, 0, 1)),
                "angleForward" : 360 * degree
            });

            var transformsInner = [];
            var namesInner = [];
            for (var i = 1; i < nInner; i += 1)
            {
                var angle = i * 360 * degree / nInner;
                transformsInner = append(transformsInner, rotationAround(line(vector(0, 0, 0) * meter, vector(0, 0, 1)), angle));
                namesInner = append(namesInner, "noz_in_" ~ i);
            }
            opPattern(context, id + "patternInner", {
                "entities" : qCreatedBy(id + "revInnerBase", EntityType.BODY),
                "transforms" : transformsInner,
                "instanceNames" : namesInner
            });

            // Outer Ring Nozzle
            var oSkId = id + "outerNozSk";
            var oSk = newSketch(context, oSkId, {"sketchPlane" : qCreatedBy(makeId("Front"), EntityType.FACE)});
            skLineSegment(oSk, "oAxis", {"start" : vector(rOuter / meter, overlapNoz / meter) * meter, "end" : vector(rOuter / meter, -LNoz / meter) * meter});
            skLineSegment(oSk, "oExit", {"start" : vector(rOuter / meter, -LNoz / meter) * meter, "end" : vector((rOuter + rNoz) / meter, -LNoz / meter) * meter});
            skLineSegment(oSk, "oWall", {"start" : vector((rOuter + rNoz) / meter, -LNoz / meter) * meter, "end" : vector((rOuter + rThroat) / meter, overlapNoz / meter) * meter});
            skLineSegment(oSk, "oTop", {"start" : vector((rOuter + rThroat) / meter, overlapNoz / meter) * meter, "end" : vector(rOuter / meter, overlapNoz / meter) * meter});
            skSolve(oSk);
            opRevolve(context, id + "revOuterBase", {
                "entities" : qSketchRegion(oSkId),
                "axis" : line(vector(rOuter / meter, 0, 0) * meter, vector(0, 0, 1)),
                "angleForward" : 360 * degree
            });

            var transformsOuter = [];
            var namesOuter = [];
            for (var i = 1; i < nOuter; i += 1)
            {
                var angle = i * 360 * degree / nOuter;
                transformsOuter = append(transformsOuter, rotationAround(line(vector(0, 0, 0) * meter, vector(0, 0, 1)), angle));
                namesOuter = append(namesOuter, "noz_out_" ~ i);
            }
            opPattern(context, id + "patternOuter", {
                "entities" : qCreatedBy(id + "revOuterBase", EntityType.BODY),
                "transforms" : transformsOuter,
                "instanceNames" : namesOuter
            });
        }

        // 4. Boolean union all solid bodies into one manifold rocket part
        var allBodies = evaluateQuery(context, qAllNonMeshSolidBodies());
        if (size(allBodies) > 1)
        {
            opBoolean(context, id + "unionAll", {
                "tools" : qAllNonMeshSolidBodies(),
                "operationType" : BooleanOperationType.UNION
            });
        }
    }
);
