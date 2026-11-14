# Draft — Automotive Software Process Engineering

> **Unapproved draft.** Human review required. Not a regulatory assessment.

## Objective

Analyze our existing software development processes and draft improved process documentation aligned with the supplied Automotive SPICE 4.1 source material. Preserve valid existing practices and distinguish gaps from missing evidence.

## Proposed content

### inputs/Automotive-SPICE-PAM-v41.pdf — page 1

Joint Quality Management in the Supply Chain Automotive SPICE® Process Reference Model Process Assessment Model Version 4.1 Title: Automotive SPICE® Process Assessment / Reference Model Author(s): VDA Working Group 13 Version: 4.1 Date: 2026-08-24 Status: Released

Source: [E0001]

### inputs/example_swe1.md — lines 1-1

# Software Requirements Procedure (illustrative)

Source: [E0002]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 25 (part 2)

iven the context, a work product is contributing to the intended purpose of the process. Context-sensitivity means that assessor judgment is needed to ensure that the actual context (application domain, business purpose, development methodology, size of the organization, etc.) is considered when using the information items. 3.3.2.2. Types of work products A work product to be considered as evidence when rating a process attribute may not necessary be outputs from the processes assessed but can also be originated from other processes of the organization. Once such a work product is used in the performance of a process under assessment, it may be considered by the assessor as objective evidence. In a lot of cases work products are comprising documentation aspects, such as specifications, re…

Source: [E0004]

### inputs/example_swe1.md — lines 3-3

The team stores software requirements in DOORS and records review outcomes.

Source: [E0005]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 30 (part 1)

1 2 3 4 ACQ.4 Supplier Monitoring Outcome Outcome Outcome Outcome Output Information Items 02-01 Commitment/Agreement X X X X 13-52 Communication evidence X X X 13-09 Meeting support evidence X X 13-14 Progress status X X 13-16 Change request X 13-19 Review evidence X 14-02 Corrective action X 15-51 Analysis results X Base Practices BP1: Agree on and maintain joint processes, joint interfaces, and information X X X to be exchanged BP2: Exchange all agreed information X X X BP3: Review development work products with the supplier X X X BP4

Source: [E0007]

### inputs/example_swe1.md — lines 5-5

## Interfaces

Source: [E0008]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 6 (part 2)

in" concept ....................................................................................... 153 Annex C.2 Integration of Machine Learning Engineering Processes .................................. 154 Annex C.3 Example of an ML Architecture ........................................................................ 156 Annex C.4 Traceability and consistency ............................................................................ 157 Annex D Reference standards ............................................................................................... 159 List of Figures Figure 1 — Process assessment model relationship ..................................................................... 13 Figure 2 — Automotive SPICE® process reference model - Overview..........................…

Source: [E0010]

### inputs/example_swe1.md — lines 7-7

Architecture receives reviewed requirements. Open questions are tracked in Jira.

Source: [E0011]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 26 (part 3)

sibly including cycles or loops, and parallelization. For example, some standards such as ISO 26262 or ISO/SAE 21434 are centered around a lifecycle model (neither of these standards in fact represents a PRM according to ISO/IEC 33004). Companies, organizational units, or projects will interpret such general lifecycle models given in standards, and then detail it out into roles, organizational interactions and interfaces, tools or tool chains, work instructions, and artifacts. Lifecycle models therefore are a concept at the HOW level (see section 3.3.3). In contrast, a PRM/PAM according to ISO/IEC 33004 (formerly ISO/IEC 15504-2) is at the level of the WHAT by abstracting from any HOW level, see Figure 3 in section 3.3.3. In Automotive SPICE®, this has been, and is, indicated by the proce…

Source: [E0012]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 159 (part 1)

Annex D Reference standards Annex D provides a list of reference standards and guidelines that support implementation of the Automotive SPICE® PAM / PRM. ISO/IEC 33001:2015 Information technology -- Process assessment – Concepts and terminology ISO/IEC 33002:2015 Information technology -- Process assessment – Requirements for performing process assessment ISO/IEC 33003:2015 Information technology -- Process assessment – Requirements for process measurement frameworks ISO/IEC 33004:2019 Information technology -- Process assessment – Requirements for process reference, process assessment and maturity models ISO/IEC 33020:2019 Information technology -- Process assessment – Process measurement framework for assessment of process capability ISO/IEC/IEEE 24765:2017 Systems and software engineer…

Source: [E0013]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 7 (part 1)

1. Introduction 1.1. Scope Process assessment is a disciplined evaluation of an organizational unit’s processes for product development against a process assessment model. The Automotive SPICE® process assessment model (PAM) is intended for use when performing conformant assessments of the process capability on the development of embedded automotive systems. It was developed in accordance with the requirements of ISO/IEC 33004:2015. The Automotive SPICE® process reference model (PRM), which was developed based on the ISO/IEC 12207, has further developed and tailored to the specific needs of the automotive industry. If processes beyond the scope of Automotive SPICE® are needed, appropriate processes from other process reference models such as ISO/IEC 12207 or ISO/IEC/IEEE 15288 may be adde…

Source: [E0014]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 14 (part 1)

3.1. Process reference model Processes are clustered into process groups according to the domain of activities they address. These process groups are organized into the process categories: Primary processes, Organizational processes and Supporting processes. For each process a purpose statement is formulated that contains the unique functional objectives of the process when performed in a particular environment. For each purpose statement a list of specific outcomes is associated, as a list of expected positive results of the process performance. For the process dimension, the Automotive SPICE® process reference model provides the set of processes shown in Figure 2. Figure 2 — Automotive SPICE® process reference model - Overview 3.1.1. Primary processes category The primary processes cate…

Source: [E0015]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 24 (part 2)

vements, an assessment obtains objective evidence. All such evidence comes either from the examination of work products related to a specific output of the processes assessed, or from statements made by the performers and managers of the processes. Sources for such evidence are either repository content of the assessed processes, or testimony provided by the performers and managers of the assessed processes. As described in chapter 3.3.1, this process assessment model provides information items serving as indicators to guide the assessor when judging a process attribute achievement. 3.3.2.1. Information items versus work products ISO/IEC 33001 provides the following definition of the term “information item”: information item separately identifiable body of information that is produced, st…

Source: [E0016]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 25 (part 1)

Information items (together with their characteristics) are provided as guidance for “what to look for” when examining the work products available in the assessed organization. The extent of implementation of an information item (in line with its defined characteristics) in a related work product serves as objective evidence supporting the assessment of a particular process. A documented process and assessor judgment is needed to ensure that the process context (application domain, business purpose, development methodology, size of the organization, etc.) is considered when using this information. Information items shall therefore not be mistaken for the work product generated by the assessed organization itself. There is no 1:1 relationship between an information item and the work produc…

Source: [E0017]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 27 (part 1)

required by the traceability/consistency Base Practices in MAN.3 or SYS.x, SWE.x, and HWE.x; • does not predefine any particular work product structure, or work product blueprints. For example, the process SYS.2 does not mean that there shall be exactly one system requirements specification or repository containing everything derived from the stakeholders. As a consequence, it is the assessor’s responsibility to map the elements in such a HOW level to the Assessment Indicators in the PAM, see Figure 4. Methods Process Assessment Model(s) Execution … mapping the information to the indicators ... Performing interviews on the actual "Doing", Investigating work products and tool repositories, … … and determine the capability profile. Reading through the defined "How" 2 3 1 Figure 4 — Performi…

Source: [E0018]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 93 (part 2)

ed, stored, analyzed, and the results interpreted. 5) Metrics are used to support decisions and provide an objective basis for communication. Base Practices MAN.6.BP1: Identify the information needs. Identify the measurement information needs that are necessary to evaluate the achievement of process objectives and work products. Note 1: Information needs may change over time. Therefore, the measurement process may be used in an iterative way. Note 2: The information needs should be aligned with the stakeholders and decision makers. MAN.6.BP2: Specify metrics. Identify and develop an appropriate set of metrics based on the measurement information needs. Note 3: Metrics may be related to processes or development results. © VDA Quality Management Center 93

Source: [E0019]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 98 (part 1)

REU.2.BP4: Ensure the qualification of the products for reuse. Provide evidence that the products for reuse are qualified for the intended use of the deliverable. Note 5: Qualification may be demonstrated by verification evidence. Note 6: Verification may include the appropriateness of documentation. REU.2.BP5: Provide the products for reuse. Make available the products to be reused to affected parties. Note 7: Refer to HWE.3, SWE.5 or SYS.4 for more information on integration of hardware, software, or system components. REU.2.BP6: Communicate information about the effectiveness of the reuse activities. Establish a communication and notification mechanism about experiences and technical outcomes to the provider of reused products. Note 8: The communication with the provider of a reused pr…

Source: [E0020]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 120 (part 1)

• the selected process quality characteristic; • the selected process measurement framework; • the selected process reference model(s); • the selected processes from the process reference model(s) in chapter 3 of this document. [ISO/IEC 33004:2015, 6.3.5 a-d] In the capability dimension, this process assessment model addresses all of the process attributes and capability levels defined in the process measurement framework. [ISO/IEC 33004:2015, 6.3.5 e] Clause 6.3.1, "Assessment indicators" Note: Due to an error in numbering in the published version of ISO/IEC 33004:2015 the following reference numbers are redundant to those stated above. To refer to the correct clauses from ISO/IEC 33004:2015, the text of clause heading is additionally specified for the following three requirements. The A…

Source: [E0021]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 153 (part 1)

Annex C Key concepts The following sections describe the key concepts that have been introduced in the Automotive SPICE® PRM resp. PAM 3.1. They relate to the terminology described in section 1.2. Annex C.1 The "Plug-in" concept The following figure shows the basic principle of the "plug-in" concept. The top-level comprises all system engineering processes organized in a system "V". Depending on the product to be developed the corresponding engineering disciplines with their domain-specific processes (e.g., hardware engineering HWE or software engineering SWE) can be added to the assessment scope. All other processes such as management processes and supporting processes are domain-independent and are therefore designed in a way that they can be applied to both the system level and the dom…

Source: [E0022]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 2 (part 2)

purpose.’ Relevant material from one of the mentioned standards is incorporated under the copyright release notice. Acknowledgement The VDA, the VDA QMC and the Project Group 13 explicitly acknowledge the high-quality work carried out by the members of the intacs® working groups. We would like to thank all involved people who have contributed to the development and publication of Automotive SPICE®. Derivative works You may not alter, transform, or build upon this work without the prior consent of the VDA Quality Management Center. Such consent may be given provided ISO copyright is not infringed. The detailed descriptions contained in this document may be incorporated as part of any tool or other material to support the performance of process assessments, so that this process assessment m…

Source: [E0023]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 4 (part 4)

Assessment indicators ........................................................................................... 23 3.3.2. Understanding information Items and work products .............................................. 24 3.3.3. Understanding the level of abstraction of a PAM .................................................... 25 3.3.4. Why a PRM and PAM are not a lifecycle model or development process blueprint 26 4. Process reference model and performance indicators (Level 1) ............................................. 28 4.1. Acquisition process group (ACQ) ................................................................................... 29 4.1.1. ACQ.4 Supplier Monitoring .................................................................................... 29 4.2. Supply process…

Source: [E0024]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 6 (part 3)

— Annex C.3: Integration of MLE Processes ................................................................ 154 Figure 7 — Annex C.3: Interdependencies within MLE and SUP.11 ........................................... 155 Figure 8 — Annex C.4: Example of an ML Architecture .............................................................. 156 Figure 9 — Annex C.4: Consistency and traceability between system and software work products ................................................................................................................................................... 157 Figure 10 — Annex C.4: Consistency and traceability between system and hardware work products ........................................................................................................................…

Source: [E0025]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 11 (part 2)

Institute of Electrical and Electronics Engineers ISO International Organization for Standardization MISRA Motor Industry Software Reliability Association ML Machine Learning ODD Operational Design Domain PA Process Attribute PAM Process Assessment Model PRM Process Reference Model RAM Random Access Memory ROM Read Only Memory SPICE Systems/Software Process Improvement and Capability dEtermination WP Work Product Table 2 — Abbreviation List © VDA Quality Management Center 11

Source: [E0026]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 24 (part 1)

Information item characteristics shall not be interpreted as a required structure of a corresponding work product, which is defined by the project and organization, respectively. Please refer to chapter 3.3.2 for understanding the difference between information items and work products. ISO 33004:2015 requires the mapping of assessment indicators to process attributes as shown in Figure 1. The capability of a process on level 1 is only characterized by the measure of the extent to which the process outcomes are achieved. According to ISO 33003:2015, a measurement framework requires each level to reveal a process attribute. Therefore, the only process performance attribute for capability Level 1 (PA.1.1) has a single generic practice (GP 1.1.1) pointing as an editorial reference to the resp…

Source: [E0027]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 28 (part 1)

4. Process reference model and performance indicators (Level 1) The processes in the process dimension can be drawn from the Automotive SPICE® process reference model, which is incorporated in the tables below indicated by a red bar at the left side. Each table related to one process in the process dimension contains the process reference model (indicated by a red bar) and the process performance indicators necessary to define the process assessment model. The process performance indicators consist of base practices (indicated by a green bar) and output information items (indicated by a blue bar). Process ID The individual processes are identified with a unique process identifier and a process name. A process purpose statement is Process name provided, and process outcomes are defined to…

Source: [E0028]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 47 (part 2)

ere may be non-functional software requirements that the software architectural design does not trace to. Examples are development process requirements. Such requirements are still subject to verification. Note 10: Bidirectional traceability supports consistency, and facilitates impact analysis of change requests, and demonstration of coverage. Traceability alone, e.g., the existence of links, does not necessarily mean that the information is consistent. SWE.2.BP5: Communicate the agreed software architecture. Communicate the agreed software architecture to all affected parties. 1 2 3 4 SWE.2 Software Architectural Design Outcome Outcome Outcome Outcome Output Information Items 04-04 Software Architecture X 13-51 Consistency Evidence X 13-52 Communication Evidence X 15-51 Analysis Results

Source: [E0029]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 51 (part 2)

s. 1 2 3 4 5 6 SWE.4 Software Unit Verification Outcome Outcome Outcome Outcome Outcome Outcome Output Information Items 08-60 Verification Measure X 03-50 Verification Measure Data X 08-58 Verification Measure Selection Set X 15-52 Verification Results X 13-51 Consistency Evidence X X 13-52 Communication Evidence X Base Practices BP1: Specify software unit verification measures X BP2: Select software unit verification measures X BP3: Verify the software units X BP4: Ensure consistency and establish bidirectional traceability for X X software unit verification BP5: Summarize and communicate the results X ©

Source: [E0030]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 90 (part 1)

MAN.3.BP5: Define and monitor the project estimates and resources. Define and monitor the project estimates of effort and resources based on the project's goals, risks, motivation and boundaries. Note 5: Examples of necessary resources are budget, people, product samples, or infrastructure. Note 6: Estimations and resources may include engineering, management and supporting processes. MAN.3.BP6: Define and monitor the required skills, knowledge, and experience. Identify and monitor the required skills, knowledge, and experience for the project in line with the estimates and work packages. Note 7: Training, mentoring or coaching of individuals may be applied to resolve deviations from required skills and knowledge. MAN.3.BP7: Define and monitor the project interfaces and agreed commitments…

Source: [E0031]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 93 (part 1)

Base Practices BP1: Identify sources of risks X BP2: Identify the potential undesirable events X BP3: Determine the risks X BP4: Define risk treatment options X X BP5: Define and perform risk treatment activities. X X BP6: Monitor the risks X BP7: Take corrective action X 4.9.3. MAN.6 Measurement Process ID MAN.6 Process name Measurement Process purpose The purpose is to collect and analyze data relating to the development results and processes implemented within the organization and its projects, to support an effective management of the processes. Process outcomes 1) The measurement information needs that are necessary to evaluate the achievement of process objectives and the achievement of desired work products are identified. 2) An appropriate set of metrics, driven by the information…

Source: [E0032]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 98 (part 2)

utcome Outcome Output Information Items 12-03 Reuse candidate X X 04-02 Domain architecture X 13-52 Communication evidence X 15-07 Reuse analysis evidence X X 13-53 Qualification evidence X Base Practices BP1: Select products for reuse X BP2: Analyze the reuse capability of the products X BP3: Define the limitations for reuse X BP4: Ensure the qualification of the products for reuse X BP5: Provide the products for reuse X BP6: Communicate information about the effectiveness of the X reuse activities © VDA Quality Management Center 98

Source: [E0033]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 100 (part 1)

5.2. Process capability Level 1: Performed process The implemented process achieves its process purpose. The following process attribute demonstrates the achievement of this level. 5.2.1. PA 1.1 Process performance process attribute Process attribute ID PA 1.1 Process attribute name Process performance Process attribute scope The process performance process attribute is a measure of the extent to which the process purpose is achieved. Process attribute achievements 1) The process achieves its defined outcomes. Generic practices GP 1.1.1 Achieve the process outcomes Achieve the intent of the base practices. Produce work products that evidence the process outcomes. a PA 1.1 Process performance process attribute Achievement Output Information Items P

Source: [E0034]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 153 (part 2)

SUP.1 SUP.8 SUP.9 SUP.10 HWE.1 HWE.4 SWE.1 SWE.6 level Domain specific HWE.2 HWE.3 SWE.2 SWE.5 PAM extension SWE.3 SWE.4 Domain Automotive SPICE 4.0 PRM/PAM SYS : System engineering SWE : Software engineering HWE : Hardware engineering Examplary processes for other domains, neither developed by VDA nor part of Automotive SPICE PRM/PAM Figure 5 — Annex C.1: The "Plug-in" concept © VDA Quality Management Center 153

Source: [E0035]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 2 (part 1)

Copyright notice This document is a revision of the Automotive SPICE® process assessment model and process reference model 4.1, which has been developed by the Working Group 13 of the Quality Management Center (QMC) in the German Association of the Automotive Industry. This document reproduces relevant material from: • ISO/IEC 33020:2019 Information technology -- Process assessment -- Process measurement framework for assessment of process capability ISO/IEC 33020:2019 provides the following copyright release statement: ‘Users of this International Standard may reproduce subclauses 5.2, 5.3, 5.4 and 5.6 as part of any process assessment model or maturity model so that it can be used for its intended purpose.’ • ISO/IEC 15504-5:2006 Information Technology – Process assessment – Part 5: An…

Source: [E0036]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 4 (part 3)

.................................. 14 3.1.1. Primary processes category ................................................................................... 14 3.1.2. Supporting processes category .............................................................................. 16 3.1.3. Organizational processes category ........................................................................ 16 3.2. Measurement framework ............................................................................................... 17 3.2.1. Process capability levels and process attributes .................................................... 17 3.2.2. Process attribute rating .......................................................................................... 18 3.2.3. Rating and aggregation method ...…

Source: [E0037]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 8 (part 1)

1.2. Terminology Automotive SPICE® follows the following precedence for use of terminology: • ISO/IEC 33001 for assessment related terminology • ISO/IEC/IEEE 24765 • Terms introduced by Automotive SPICE® • PMBOK® Guide – Fourth Edition • PAS 1883:2020 • Oxford Dictionary Term Origin Description Activity Automotive Execution of a task by a stakeholder or an involved party. SPICE® V4.0 Application Automotive An application parameter is a software variable containing data that parameter SPICE® V4.0 can be changed at the system or software levels; they influence the system’s or software behavior and properties. The notion of application parameter is expressed in two ways: • The specification (including variable names, the domain value range, technical data types, default values, physical unit…

Source: [E0038]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 10 (part 1)

Software Automotive Software component in design and implementation-oriented component SPICE® processes: V4.0 The software architecture decomposes the software into software components across appropriate hierarchical levels down to the lowest-level software components in a conceptual model. Software component in verification-oriented processes: The implementation of a SW component under verification is represented, e.g., as source code, object files, library file, executable, or executable model. Software Automotive A software element is subject to integration within the software. element SPICE® V4.0 Can represent a →SOFTWARE COMPONENT or →SOFTWARE UNIT Software unit Automotive Software unit in design and implementation-oriented processes: SPICE® V4.0 As a result of the decomposition of a…

Source: [E0039]

### inputs/Automotive-SPICE-PAM-v41.pdf — page 10 (part 2)

l model, the software is decomposed into software units. A software unit is decided not to be further subdivided. Software unit in verification-oriented processes: An implemented SW unit under verification is represented, e.g., as source code files, or an object file. Stakeholder Automotive Any type of requirement for the stakeholders in the given context, requirements SPICE® V4.0 e.g., customer requirement, supplier internal requirements (product-specific, platform etc.), legal requirements, regulatory requirements, statutory requirements, industry sector requirements, international standards, codes of practice etc. … System Automotive A collection of interacting components organized to accomplish a SPICE® V4.0 specific function or set of functions within a specific environment. System A…

Source: [E0040]

## Unresolved questions

- Are all relevant documents and revisions included?
- Are the source interpretations correct?
- Which changes or decisions require document-owner approval?
